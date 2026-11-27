"""Real price on bookings, server-side room choice, the door code and the demo reset."""

import itertools
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from sqlalchemy import func, select

from server import door_access
from server.auth import issue_guest_token
from server.booking_service import CHECKED_IN, check_in, check_out
from server.demo_reset import wipe
from server.models import Booking, Guest, StaffUser
from server.rooms import assign_room
from server.timeutil import utcnow
from server.ttlock import TTLockError, get_ttlock

STAFF_KEY = "test-staff-key-0123456789-0123456789"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


# ---------- the door code ----------


async def test_check_in_makes_a_door_code(session, make_booking):
    booking = await make_booking()
    result = await check_in(session, booking)

    assert result["door_pin_issued"] is True
    assert re.fullmatch(r"[1-9]\d{5}", booking.door_pin)
    assert booking.door_pin_id is not None
    assert booking.door_pin_expires > utcnow()
    stored = get_ttlock().passcodes[booking.door_pin_id]
    assert stored["pin"] == booking.door_pin


async def test_code_stops_at_checkout_time_on_departure_day(session, make_booking):
    booking = await make_booking()
    booking.planned_check_out = datetime(2099, 1, 3)
    await check_in(session, booking)
    assert booking.door_pin_expires == datetime(2099, 1, 3, 12, 0)


async def test_checkout_time_is_in_the_hotel_time_zone(session, make_booking, monkeypatch):
    try:
        ZoneInfo("Asia/Beirut")
    except ZoneInfoNotFoundError:
        pytest.skip("time zone data missing: pip install tzdata")
    monkeypatch.setenv("HOTEL_TIMEZONE", "Asia/Beirut")
    booking = await make_booking()
    booking.planned_check_out = datetime(2099, 1, 3)  # January: Beirut is UTC+2
    await check_in(session, booking)
    assert booking.door_pin_expires == datetime(2099, 1, 3, 10, 0)


async def test_checkout_hour_can_be_changed(session, make_booking, monkeypatch):
    monkeypatch.setenv("CHECKOUT_HOUR", "11")
    booking = await make_booking()
    booking.planned_check_out = datetime(2099, 1, 3)
    await check_in(session, booking)
    assert booking.door_pin_expires == datetime(2099, 1, 3, 11, 0)


async def test_check_out_removes_the_code(session, make_booking):
    booking = await make_booking()
    await check_in(session, booking)
    assert get_ttlock().passcodes
    await check_out(session, booking)
    assert booking.door_pin is None
    assert booking.door_pin_id is None
    assert get_ttlock().passcodes == {}


async def test_check_in_still_works_when_tt_lock_fails(session, make_booking, monkeypatch):
    class Broken:
        mode = "sim"

        async def add_passcode(self, *args, **kwargs):
            raise TTLockError("TT Lock error -3009: memory full", -3009)

    monkeypatch.setattr(door_access, "get_ttlock", lambda: Broken())
    booking = await make_booking()
    result = await check_in(session, booking)

    assert booking.status == CHECKED_IN
    assert booking.door_pin is None
    assert result["door_pin_issued"] is False
    assert "-3009" in result["door_pin_error"]


async def test_no_code_when_a_live_room_has_no_lock_id(session, make_booking, monkeypatch):
    class Live:
        mode = "live"

    monkeypatch.setattr(door_access, "get_ttlock", lambda: Live())
    booking = await make_booking()
    result = await check_in(session, booking)

    assert booking.status == CHECKED_IN
    assert result["door_pin_issued"] is False
    assert "No lock is set up for room1" in result["door_pin_error"]


async def test_lock_ids_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("TTLOCK_LOCK_IDS", "room1:1111, room2:2222")
    assert door_access.lock_id_for("room1") == 1111
    assert door_access.lock_id_for("room2") == 2222


# ---------- choosing a room ----------


async def stay(session, make_booking, room_id, arrival, departure):
    booking = await make_booking(room_id=room_id)
    booking.planned_check_in = arrival
    booking.planned_check_out = departure
    await session.commit()
    return booking


async def test_first_free_room_is_chosen(session):
    assert await assign_room(session, datetime(2099, 1, 1), datetime(2099, 1, 3)) == "room1"


async def test_overlapping_stay_moves_the_guest_to_the_next_room(session, make_booking):
    await stay(session, make_booking, "room1", datetime(2099, 1, 1), datetime(2099, 1, 5))
    assert await assign_room(session, datetime(2099, 1, 3), datetime(2099, 1, 6)) == "room2"


async def test_back_to_back_stays_share_a_room(session, make_booking):
    await stay(session, make_booking, "room1", datetime(2099, 1, 1), datetime(2099, 1, 5))
    assert await assign_room(session, datetime(2099, 1, 5), datetime(2099, 1, 7)) == "room1"


async def test_no_room_when_all_are_taken(session, make_booking):
    await stay(session, make_booking, "room1", datetime(2099, 1, 1), datetime(2099, 1, 5))
    await stay(session, make_booking, "room2", datetime(2099, 1, 2), datetime(2099, 1, 4))
    assert await assign_room(session, datetime(2099, 1, 3), datetime(2099, 1, 4)) is None


async def test_assignable_rooms_can_be_changed(session, monkeypatch):
    monkeypatch.setenv("ASSIGNABLE_ROOMS", "room5, room6")
    assert await assign_room(session, datetime(2099, 1, 1), datetime(2099, 1, 2)) == "room5"


# ---------- the whole flow through the API ----------


class FakeApaleo:
    property_id = "TEST"

    def __init__(self):
        self.count = itertools.count(1)

    async def get_offers(self, property_id, arrival, departure, adults):
        return [
            {
                "ratePlan": {"id": "RP1", "name": "Flexible"},
                "unitGroup": {"name": "Double"},
                "totalGrossAmount": {"amount": 216.0, "currency": "EUR"},
                "minGuaranteeType": "PM6Hold",
            }
        ]

    async def create_booking(self, offer, arrival, departure, adults, first, last, email):
        n = next(self.count)
        return {"id": f"BK{n}", "reservationIds": [{"id": f"BK{n}-1"}]}


@pytest.fixture
def apaleo(monkeypatch):
    fake = FakeApaleo()
    monkeypatch.setattr("server.main.get_client", lambda: fake)
    return fake


async def book(client, session, n=1):
    guest = Guest(name=f"Guest {n}", email=f"g{n}@example.com")
    session.add(guest)
    await session.commit()
    arrival = date.today() + timedelta(days=30)
    response = await client.post(
        "/bookings/apaleo",
        json={
            "guest_id": guest.id,
            "arrival": arrival.isoformat(),
            "departure": (arrival + timedelta(days=2)).isoformat(),
            "adults": 2,
            "rate_plan_id": "RP1",
        },
    )
    return response


async def test_booking_stores_the_quoted_price(client, session, apaleo):
    response = await book(client, session)
    assert response.status_code == 200
    body = response.json()
    detail = await client.get(
        f"/bookings/{body['id']}", headers=bearer(body["guest_token"])
    )
    assert detail.json()["total_cents"] == 21600
    assert detail.json()["currency"] == "EUR"


async def test_the_server_picks_the_room_and_runs_out(client, session, apaleo):
    first = await book(client, session, 1)
    second = await book(client, session, 2)
    third = await book(client, session, 3)
    assert first.json()["room_id"] == "room1"
    assert second.json()["room_id"] == "room2"
    assert third.status_code == 409


async def test_a_full_hotel_does_not_create_an_apaleo_reservation(client, session, apaleo):
    await book(client, session, 1)
    await book(client, session, 2)
    before = next(apaleo.count)
    await book(client, session, 3)
    assert next(apaleo.count) == before + 1  # nothing was created for the third guest


async def test_guest_sees_the_door_code_but_the_booking_list_hides_it(client, session, apaleo):
    created = (await book(client, session)).json()
    headers = bearer(created["guest_token"])

    before = await client.get(f"/bookings/{created['id']}", headers=headers)
    assert before.json()["door_pin"] is None

    checked_in = await client.post(f"/bookings/{created['id']}/checkin", headers=headers)
    assert checked_in.status_code == 200
    assert checked_in.json()["door_pin_issued"] is True
    assert "door_pin" not in checked_in.json()

    after = await client.get(f"/bookings/{created['id']}", headers=headers)
    assert re.fullmatch(r"[1-9]\d{5}", after.json()["door_pin"])
    assert after.json()["door_pin_expires"] is not None

    listing = await client.get("/bookings", headers=bearer(STAFF_KEY))
    assert all("door_pin" not in row for row in listing.json())


async def test_receipt_uses_the_stored_price(client, session, apaleo):
    created = (await book(client, session)).json()
    headers = bearer(created["guest_token"])
    await client.post(f"/bookings/{created['id']}/checkin", headers=headers)
    await client.post(f"/bookings/{created['id']}/checkout", headers=headers)

    receipt = (await client.get(f"/bookings/{created['id']}/summary", headers=headers)).json()
    assert receipt["room_charge_cents"] == 21600
    assert receipt["currency"] == "EUR"
    assert receipt["nights"] == 2


async def test_old_bookings_without_a_price_use_the_demo_rate(client, session, make_booking):
    booking = await make_booking()
    headers = bearer(await issue_guest_token(session, booking))
    await session.commit()
    await client.post(f"/bookings/{booking.id}/checkin", headers=headers)
    await client.post(f"/bookings/{booking.id}/checkout", headers=headers)

    receipt = (await client.get(f"/bookings/{booking.id}/summary", headers=headers)).json()
    assert receipt["room_charge_cents"] == 22000
    assert receipt["currency"] == "USD"


# ---------- demo reset ----------


async def test_reset_clears_the_demo_but_keeps_staff(session, make_booking):
    await make_booking()
    session.add(StaffUser(username="desk1", name="Desk", role="front_desk", password_hash="x"))
    await session.commit()

    counts = await wipe(session)

    assert counts["bookings"] == 1
    assert counts["guests"] == 1
    for model in (Booking, Guest):
        assert (await session.execute(select(func.count()).select_from(model))).scalar_one() == 0
    assert (await session.execute(select(func.count()).select_from(StaffUser))).scalar_one() == 1
