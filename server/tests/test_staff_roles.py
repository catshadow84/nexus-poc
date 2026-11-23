import pytest

from server.auth import issue_guest_token
from server.passwords import reset_throttle
from server.staff import create_staff

STAFF_KEY = "test-staff-key-0123456789-0123456789"
PASSWORD = "a long enough password"
LIGHT = {"power": "on", "brightness": 40, "color": "warm"}


@pytest.fixture(autouse=True)
def role_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    reset_throttle()
    yield
    reset_throttle()


@pytest.fixture
def as_role(client, session):
    """as_role("housekeeping") -> request headers for a logged-in housekeeper."""
    cache: dict[str, dict] = {}

    async def _headers(role: str) -> dict:
        if role not in cache:
            username = f"{role}-user".replace("_", "-")
            await create_staff(session, username, f"Test {role}", role, PASSWORD)
            response = await client.post(
                "/staff/login", json={"username": username, "password": PASSWORD}
            )
            assert response.status_code == 200
            cache[role] = {"Authorization": f"Bearer {response.json()['token']}"}
        return cache[role]

    return _headers


async def statuses(client, as_role, method, url, roles, **kwargs):
    result = {}
    for role in roles:
        response = await client.request(method, url, headers=await as_role(role), **kwargs)
        result[role] = response.status_code
    return result


ALL_ROLES = ["front_desk", "housekeeping", "maintenance", "manager"]


async def test_bookings_list_is_front_desk_and_manager_only(client, as_role, make_booking):
    await make_booking()
    assert await statuses(client, as_role, "GET", "/bookings", ALL_ROLES) == {
        "front_desk": 200, "housekeeping": 403, "maintenance": 403, "manager": 200,
    }


async def test_one_booking_and_its_guest_are_hidden_from_housekeeping_and_maintenance(
    client, as_role, make_booking
):
    booking = await make_booking()
    expected = {"front_desk": 200, "housekeeping": 404, "maintenance": 404, "manager": 200}
    assert await statuses(client, as_role, "GET", f"/bookings/{booking.id}", ALL_ROLES) == expected
    assert await statuses(client, as_role, "GET", f"/guests/{booking.guest_id}", ALL_ROLES) == expected


async def test_overview_and_search_are_front_desk_and_manager_only(client, as_role, make_booking):
    await make_booking()
    expected = {"front_desk": 200, "housekeeping": 403, "maintenance": 403, "manager": 200}
    assert await statuses(client, as_role, "GET", "/staff/overview", ALL_ROLES) == expected
    assert await statuses(client, as_role, "GET", "/staff/search?q=guest", ALL_ROLES) == expected


async def test_every_staff_role_can_list_rooms_but_a_guest_cannot(client, session, as_role, make_booking):
    assert await statuses(client, as_role, "GET", "/rooms", ALL_ROLES) == {
        "front_desk": 200, "housekeeping": 200, "maintenance": 200, "manager": 200,
    }
    booking = await make_booking()
    guest = {"Authorization": f"Bearer {await issue_guest_token(session, booking)}"}
    await session.commit()
    assert (await client.get("/rooms", headers=guest)).status_code == 403


async def test_housekeeping_cannot_control_devices_but_maintenance_can(client, as_role, published):
    result = await statuses(
        client, as_role, "POST", "/rooms/room1/device/light/command", ALL_ROLES, json=LIGHT
    )
    assert result == {"front_desk": 200, "housekeeping": 403, "maintenance": 200, "manager": 200}


async def test_the_old_shared_key_can_still_do_everything(client, make_booking):
    booking = await make_booking()
    key = {"Authorization": f"Bearer {STAFF_KEY}"}
    assert (await client.get("/bookings", headers=key)).status_code == 200
    assert (await client.get(f"/bookings/{booking.id}", headers=key)).status_code == 200
    assert (await client.post("/rooms/room1/device/light/command", json=LIGHT, headers=key)).status_code == 200