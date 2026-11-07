from datetime import timedelta

import pytest
from sqlalchemy import select

from server.auth import hash_token, issue_guest_token
from server.booking_service import check_in, check_out
from server.models import AccessToken, Guest
from server.timeutil import utcnow

STAFF_KEY = "test-staff-key-0123456789-0123456789"
LIGHT = {"power": "on", "brightness": 40, "color": "warm"}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


STAFF = bearer(STAFF_KEY)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


async def guest_headers(session, booking) -> dict:
    token = await issue_guest_token(session, booking)
    await session.commit()
    return bearer(token)


async def test_health_and_scenes_stay_public(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/scenes")).status_code == 200


async def test_no_token_is_rejected(client, make_booking):
    booking = await make_booking()
    assert (await client.get(f"/bookings/{booking.id}")).status_code == 401


async def test_invalid_token_is_rejected(client, make_booking):
    booking = await make_booking()
    response = await client.get(f"/bookings/{booking.id}", headers=bearer("nonsense"))
    assert response.status_code == 401


async def test_staff_can_read_any_booking_and_list_all(client, make_booking):
    booking = await make_booking()
    assert (await client.get(f"/bookings/{booking.id}", headers=STAFF)).status_code == 200
    listing = await client.get("/bookings", headers=STAFF)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_staff_access_is_off_when_no_key_is_configured(client, make_booking, monkeypatch):
    monkeypatch.delenv("STAFF_API_KEY")
    booking = await make_booking()
    assert (await client.get(f"/bookings/{booking.id}", headers=STAFF)).status_code == 401


async def test_guest_reads_own_booking_but_not_someone_elses(client, session, make_booking):
    mine = await make_booking(room_id="room1")
    other = await make_booking(room_id="room2")
    headers = await guest_headers(session, mine)
    assert (await client.get(f"/bookings/{mine.id}", headers=headers)).status_code == 200
    assert (await client.get(f"/bookings/{other.id}", headers=headers)).status_code == 404


async def test_guest_cannot_use_staff_endpoints(client, session, make_booking):
    booking = await make_booking()
    headers = await guest_headers(session, booking)
    for path in ("/bookings", "/rooms", "/bookings/active"):
        assert (await client.get(path, headers=headers)).status_code == 403
    lookup = await client.get("/guests/lookup", params={"email": "x@y.com"}, headers=headers)
    assert lookup.status_code == 403
    reissue = await client.post(f"/bookings/{booking.id}/token", headers=headers)
    assert reissue.status_code == 403


async def test_guest_cannot_reach_the_room_before_check_in(client, session, make_booking):
    booking = await make_booking(room_id="room1")
    headers = await guest_headers(session, booking)
    assert (await client.get("/rooms/room1/state", headers=headers)).status_code == 403


async def test_guest_reaches_only_their_own_room_while_checked_in(client, session, make_booking):
    booking = await make_booking(room_id="room1")
    headers = await guest_headers(session, booking)
    await check_in(session, booking)
    assert (await client.get("/rooms/room1/state", headers=headers)).status_code == 200
    assert (await client.get("/rooms/room2/state", headers=headers)).status_code == 403


async def test_guest_can_command_own_room_but_not_another(client, session, make_booking):
    booking = await make_booking(room_id="room1")
    headers = await guest_headers(session, booking)
    await check_in(session, booking)
    own = await client.post("/rooms/room1/device/light/command", json=LIGHT, headers=headers)
    other = await client.post("/rooms/room2/device/light/command", json=LIGHT, headers=headers)
    assert own.status_code == 200
    assert other.status_code == 403


async def test_guest_loses_the_room_after_check_out(client, session, make_booking):
    booking = await make_booking(room_id="room1")
    headers = await guest_headers(session, booking)
    await check_in(session, booking)
    await check_out(session, booking)
    assert (await client.get("/rooms/room1/state", headers=headers)).status_code == 403
    # but the guest can still read their own summary
    assert (await client.get(f"/bookings/{booking.id}/summary", headers=headers)).status_code == 200


async def test_reissuing_a_token_revokes_the_old_one(client, session, make_booking):
    booking = await make_booking()
    old = await guest_headers(session, booking)
    response = await client.post(f"/bookings/{booking.id}/token", headers=STAFF)
    assert response.status_code == 200
    new = bearer(response.json()["guest_token"])
    assert (await client.get(f"/bookings/{booking.id}", headers=old)).status_code == 401
    assert (await client.get(f"/bookings/{booking.id}", headers=new)).status_code == 200


async def test_expired_token_is_rejected(client, session, make_booking):
    booking = await make_booking()
    headers = await guest_headers(session, booking)
    row = (await session.execute(select(AccessToken))).scalars().first()
    row.expires_at = utcnow() - timedelta(minutes=1)
    await session.commit()
    assert (await client.get(f"/bookings/{booking.id}", headers=headers)).status_code == 401


async def test_tokens_are_stored_hashed(session, make_booking):
    booking = await make_booking()
    token = await issue_guest_token(session, booking)
    await session.commit()
    row = (await session.execute(select(AccessToken))).scalars().first()
    assert row.token_hash == hash_token(token)
    assert row.token_hash != token


async def test_nora_needs_a_token_and_a_checked_in_booking(client, session, make_booking):
    booking = await make_booking()
    headers = await guest_headers(session, booking)
    body = {"session_id": "s1", "message": "hello", "booking_id": booking.id}
    assert (await client.post("/nora/chat", json=body)).status_code == 401
    assert (await client.post("/nora/chat", json=body, headers=headers)).status_code == 403


async def test_anonymous_callers_cannot_overwrite_an_existing_guest(client, session, make_booking):
    booking = await make_booking()
    guest = await session.get(Guest, booking.guest_id)
    body = {
        "name": "Hacker",
        "email": guest.email,
        "preferences": {"curtain": {"open_pct": 100}},
    }
    await client.post("/guests", json=body)
    await session.refresh(guest)
    assert guest.name != "Hacker"
    assert "curtain" not in guest.preferences

    await client.post("/guests", json=body, headers=STAFF)
    await session.refresh(guest)
    assert guest.name == "Hacker"


async def test_auth_disabled_flag_opens_everything(client, make_booking, monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    await make_booking()
    assert (await client.get("/bookings")).status_code == 200