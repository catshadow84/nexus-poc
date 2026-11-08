import pytest

from server.apaleo import ApaleoError
from server.auth import issue_guest_token
from server.booking_service import CANCELED, RESERVED, check_in

STAFF_KEY = "test-staff-key-0123456789-0123456789"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


async def headers_for(session, booking) -> dict:
    token = await issue_guest_token(session, booking)
    await session.commit()
    return {"Authorization": f"Bearer {token}"}


class FakeApaleo:
    def __init__(self, fail=False):
        self.fail = fail
        self.canceled = []

    async def cancel_reservation(self, reservation_id):
        if self.fail:
            raise ApaleoError("boom")
        self.canceled.append(reservation_id)


async def test_guest_cancels_a_reservation(client, session, make_booking, monkeypatch):
    fake = FakeApaleo()
    monkeypatch.setattr("server.main.get_client", lambda: fake)
    booking = await make_booking()
    booking.apaleo_reservation_id = "ABC-1"
    await session.commit()
    headers = await headers_for(session, booking)

    response = await client.post(f"/bookings/{booking.id}/cancel", headers=headers)

    assert response.status_code == 200
    assert fake.canceled == ["ABC-1"]
    await session.refresh(booking)
    assert booking.status == CANCELED


async def test_cannot_cancel_after_check_in(client, session, make_booking, monkeypatch):
    monkeypatch.setattr("server.main.get_client", lambda: FakeApaleo())
    booking = await make_booking()
    headers = await headers_for(session, booking)
    await check_in(session, booking)

    response = await client.post(f"/bookings/{booking.id}/cancel", headers=headers)
    assert response.status_code == 400


async def test_failed_apaleo_cancel_leaves_the_booking_alone(client, session, make_booking, monkeypatch):
    monkeypatch.setattr("server.main.get_client", lambda: FakeApaleo(fail=True))
    booking = await make_booking()
    booking.apaleo_reservation_id = "ABC-1"
    await session.commit()
    headers = await headers_for(session, booking)

    response = await client.post(f"/bookings/{booking.id}/cancel", headers=headers)

    assert response.status_code == 502
    await session.refresh(booking)
    assert booking.status == RESERVED


async def test_cannot_order_before_check_in(client, session, make_booking):
    booking = await make_booking()
    headers = await headers_for(session, booking)
    response = await client.post(
        f"/bookings/{booking.id}/orders", json={"item": "coffee", "quantity": 1}, headers=headers
    )
    assert response.status_code == 400


async def test_order_appears_on_the_bill(client, session, make_booking):
    booking = await make_booking()
    headers = await headers_for(session, booking)
    await check_in(session, booking)

    response = await client.post(
        f"/bookings/{booking.id}/orders", json={"item": "Coffee", "quantity": 2}, headers=headers
    )
    assert response.status_code == 200

    summary = (await client.get(f"/bookings/{booking.id}/summary", headers=headers)).json()
    assert summary["orders_total_cents"] == 900  # 2 x 450 from the server's menu


async def test_unknown_item_is_rejected(client, session, make_booking):
    booking = await make_booking()
    headers = await headers_for(session, booking)
    await check_in(session, booking)
    response = await client.post(
        f"/bookings/{booking.id}/orders", json={"item": "caviar", "quantity": 1}, headers=headers
    )
    assert response.status_code == 422


async def test_guest_cannot_touch_someone_elses_booking(client, session, make_booking):
    mine = await make_booking()
    theirs = await make_booking()
    headers = await headers_for(session, mine)
    await check_in(session, theirs)

    cancel = await client.post(f"/bookings/{theirs.id}/cancel", headers=headers)
    order = await client.post(
        f"/bookings/{theirs.id}/orders", json={"item": "tea", "quantity": 1}, headers=headers
    )
    assert cancel.status_code == 404
    assert order.status_code == 404