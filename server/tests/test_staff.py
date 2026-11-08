from datetime import datetime, time as dtime

import pytest

from server.auth import issue_guest_token
from server.booking_service import check_in
from server.timeutil import utcnow

STAFF_KEY = "test-staff-key-0123456789-0123456789"
STAFF = {"Authorization": f"Bearer {STAFF_KEY}"}


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


async def headers_for(session, booking) -> dict:
    token = await issue_guest_token(session, booking)
    await session.commit()
    return {"Authorization": f"Bearer {token}"}


def today_midnight():
    return datetime.combine(utcnow().date(), dtime.min)


async def test_overview_lists_todays_arrival(client, session, make_booking):
    booking = await make_booking()
    booking.planned_check_in = today_midnight()
    await session.commit()

    data = (await client.get("/staff/overview", headers=STAFF)).json()
    assert [r["booking_id"] for r in data["arrivals"]] == [booking.id]
    assert data["in_house"] == []


async def test_overview_lists_in_house_and_departure(client, session, make_booking):
    booking = await make_booking()
    booking.planned_check_out = today_midnight()
    await session.commit()
    await check_in(session, booking)

    data = (await client.get("/staff/overview", headers=STAFF)).json()
    assert [r["booking_id"] for r in data["in_house"]] == [booking.id]
    assert [r["booking_id"] for r in data["departures"]] == [booking.id]


async def test_staff_endpoints_reject_guests(client, session, make_booking):
    booking = await make_booking()
    headers = await headers_for(session, booking)
    assert (await client.get("/staff/overview", headers=headers)).status_code == 403
    assert (await client.get("/staff/search?q=guest", headers=headers)).status_code == 403


async def test_search_finds_by_name_and_reservation(client, session, make_booking):
    booking = await make_booking()
    booking.apaleo_reservation_id = "XYZ123-1"
    await session.commit()

    by_name = (await client.get("/staff/search?q=guest", headers=STAFF)).json()
    by_res = (await client.get("/staff/search?q=xyz123", headers=STAFF)).json()
    assert booking.id in [r["booking_id"] for r in by_name]
    assert [r["booking_id"] for r in by_res] == [booking.id]
    assert (await client.get("/staff/search?q=a", headers=STAFF)).status_code == 422


async def test_guest_edits_own_profile_but_not_others(client, session, make_booking):
    mine = await make_booking()
    theirs = await make_booking()
    headers = await headers_for(session, mine)

    ok = await client.patch(f"/guests/{mine.guest_id}", json={"name": "New Name"}, headers=headers)
    other = await client.patch(f"/guests/{theirs.guest_id}", json={"name": "Hacked"}, headers=headers)
    assert ok.status_code == 200 and ok.json()["name"] == "New Name"
    assert other.status_code == 404