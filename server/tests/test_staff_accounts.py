import pytest

from server.passwords import reset_throttle
from server.staff import create_staff

STAFF_KEY = "test-staff-key-0123456789-0123456789"
PASSWORD = "a long enough password"


@pytest.fixture(autouse=True)
def staff_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    reset_throttle()
    yield
    reset_throttle()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def login(client, username, password=PASSWORD):
    return await client.post("/staff/login", json={"username": username, "password": password})


@pytest.fixture
def staff_headers(client, session):
    """Returns a function: create an account with a role, log in, give back its headers."""

    async def _make(role="manager", username=None):
        username = username or f"{role}-user"
        await create_staff(session, username, f"Test {role}", role, PASSWORD)
        response = await login(client, username)
        assert response.status_code == 200
        return bearer(response.json()["token"])

    return _make


async def test_login_gives_a_token_that_works(client, session):
    await create_staff(session, "Amal", "Amal K", "front_desk", PASSWORD)
    response = await login(client, "  AMAL ")  # name is case-insensitive
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "front_desk" and body["name"] == "Amal K"
    me = await client.get("/staff/me", headers=bearer(body["token"]))
    assert me.status_code == 200 and me.json()["username"] == "amal"
    assert "password" not in me.text


async def test_wrong_password_and_unknown_name_look_the_same(client, session):
    await create_staff(session, "amal", "Amal K", "front_desk", PASSWORD)
    wrong = await login(client, "amal", "not the password")
    unknown = await login(client, "nobody", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_five_wrong_attempts_lock_the_account_for_a_while(client, session):
    await create_staff(session, "amal", "Amal K", "front_desk", PASSWORD)
    for _ in range(5):
        assert (await login(client, "amal", "wrong wrong wrong")).status_code == 401
    assert (await login(client, "amal", PASSWORD)).status_code == 429


async def test_an_inactive_account_cannot_log_in(client, session, staff_headers):
    manager = await staff_headers("manager")
    created = await client.post(
        "/staff/accounts",
        json={"username": "omar", "name": "Omar", "role": "maintenance", "password": PASSWORD},
        headers=manager,
    )
    assert created.status_code == 201
    await client.patch(f"/staff/accounts/{created.json()['id']}", json={"active": False}, headers=manager)
    assert (await login(client, "omar")).status_code == 401


async def test_deactivating_an_account_kills_its_open_session(client, session, staff_headers):
    manager = await staff_headers("manager")
    desk = await staff_headers("front_desk", "desk1")
    assert (await client.get("/staff/me", headers=desk)).status_code == 200
    desk_id = (await client.get("/staff/me", headers=desk)).json()["id"]
    await client.patch(f"/staff/accounts/{desk_id}", json={"active": False}, headers=manager)
    assert (await client.get("/staff/me", headers=desk)).status_code == 401


async def test_only_managers_manage_accounts(client, session, staff_headers, make_booking):
    manager = await staff_headers("manager")
    desk = await staff_headers("front_desk", "desk1")
    assert (await client.get("/staff/accounts", headers=manager)).status_code == 200
    assert (await client.get("/staff/accounts", headers=desk)).status_code == 403
    assert (await client.get("/staff/accounts")).status_code == 401
    booking = await make_booking()
    from server.auth import issue_guest_token

    guest = bearer(await issue_guest_token(session, booking))
    await session.commit()
    assert (await client.get("/staff/accounts", headers=guest)).status_code == 403


async def test_account_list_never_shows_password_hashes(client, session, staff_headers):
    manager = await staff_headers("manager")
    listing = await client.get("/staff/accounts", headers=manager)
    assert "scrypt" not in listing.text and "password" not in listing.text


async def test_creating_accounts_checks_its_input(client, session, staff_headers):
    manager = await staff_headers("manager")

    def body(**changes):
        data = {"username": "newperson", "name": "New Person", "role": "housekeeping", "password": PASSWORD}
        return {**data, **changes}

    assert (await client.post("/staff/accounts", json=body(password="short"), headers=manager)).status_code == 400
    assert (await client.post("/staff/accounts", json=body(username="a b"), headers=manager)).status_code == 400
    assert (await client.post("/staff/accounts", json=body(role="boss"), headers=manager)).status_code == 422
    assert (await client.post("/staff/accounts", json=body(), headers=manager)).status_code == 201
    assert (await client.post("/staff/accounts", json=body(), headers=manager)).status_code == 400  # taken


async def test_a_manager_cannot_lock_themselves_out(client, session, staff_headers):
    manager = await staff_headers("manager")
    my_id = (await client.get("/staff/me", headers=manager)).json()["id"]
    assert (await client.patch(f"/staff/accounts/{my_id}", json={"active": False}, headers=manager)).status_code == 400
    assert (await client.patch(f"/staff/accounts/{my_id}", json={"role": "front_desk"}, headers=manager)).status_code == 400


async def test_changing_a_password_signs_that_person_out(client, session, staff_headers):
    manager = await staff_headers("manager")
    desk = await staff_headers("front_desk", "desk1")
    desk_id = (await client.get("/staff/me", headers=desk)).json()["id"]
    await client.patch(f"/staff/accounts/{desk_id}", json={"password": "a brand new password"}, headers=manager)
    assert (await client.get("/staff/me", headers=desk)).status_code == 401
    assert (await login(client, "desk1")).status_code == 401
    assert (await login(client, "desk1", "a brand new password")).status_code == 200


async def test_logout_ends_the_session(client, session, staff_headers):
    desk = await staff_headers("front_desk", "desk1")
    assert (await client.post("/staff/logout", headers=desk)).status_code == 200
    assert (await client.get("/staff/me", headers=desk)).status_code == 401


async def test_staff_accounts_reach_the_existing_staff_endpoints(client, session, staff_headers, make_booking):
    desk = await staff_headers("front_desk", "desk1")
    await make_booking()
    assert (await client.get("/bookings", headers=desk)).status_code == 200


async def test_the_old_shared_key_still_works_as_a_manager(client):
    key = bearer(STAFF_KEY)
    me = await client.get("/staff/me", headers=key)
    assert me.status_code == 200 and me.json()["role"] == "manager"
    assert (await client.get("/staff/accounts", headers=key)).status_code == 200