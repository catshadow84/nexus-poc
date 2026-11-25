import pytest

from server.booking_service import check_in, check_out
from server.models import RoomStatus
from server.passwords import reset_throttle
from server.staff import create_staff

PASSWORD = "a long enough password"


@pytest.fixture(autouse=True)
def ops_env(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("HOTEL_ROOMS", raising=False)
    reset_throttle()
    yield
    reset_throttle()


@pytest.fixture
def as_role(client, session):
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


def by_room(body):
    return {r["room_id"]: r for r in body["rooms"]}


async def test_check_out_marks_the_room_dirty(session, make_booking):
    booking = await make_booking(room_id="room1")
    await check_in(session, booking)
    await check_out(session, booking)
    status = await session.get(RoomStatus, "room1")
    assert status.clean_state == "dirty"
    assert status.updated_by == "check-out"


async def test_housekeeping_sees_every_hotel_room_clean_by_default(client, as_role):
    response = await client.get("/housekeeping/rooms", headers=await as_role("housekeeping"))
    assert response.status_code == 200
    body = response.json()
    assert sorted(by_room(body)) == [f"room{n}" for n in range(1, 7)]
    assert all(r["clean_state"] == "clean" and not r["occupied"] for r in body["rooms"])
    assert body["summary"] == {"dirty": 0, "cleaning": 0, "clean": 6, "inspected": 0}


async def test_the_room_list_can_be_set_in_the_environment(client, as_role, monkeypatch):
    monkeypatch.setenv("HOTEL_ROOMS", "101, 102")
    response = await client.get("/housekeeping/rooms", headers=await as_role("housekeeping"))
    assert sorted(by_room(response.json())) == ["101", "102"]


async def test_an_occupied_room_shows_as_occupied_and_checkout_makes_it_dirty(
    client, session, as_role, make_booking
):
    desk = await as_role("front_desk")
    booking = await make_booking(room_id="room1")
    await check_in(session, booking)
    rooms = by_room((await client.get("/housekeeping/rooms", headers=desk)).json())
    assert rooms["room1"]["occupied"] is True
    await check_out(session, booking)
    rooms = by_room((await client.get("/housekeeping/rooms", headers=desk)).json())
    assert rooms["room1"]["occupied"] is False and rooms["room1"]["clean_state"] == "dirty"


async def test_housekeeping_can_start_and_finish_cleaning_but_not_inspect(client, as_role):
    keeper = await as_role("housekeeping")
    for state in ("cleaning", "clean"):
        response = await client.post("/housekeeping/rooms/room2/status", json={"state": state}, headers=keeper)
        assert response.status_code == 200
        assert response.json()["clean_state"] == state
        assert response.json()["updated_by"] == "Test housekeeping"
    for state in ("inspected", "dirty"):
        response = await client.post("/housekeeping/rooms/room2/status", json={"state": state}, headers=keeper)
        assert response.status_code == 403


async def test_front_desk_can_inspect_and_set_any_state(client, as_role):
    desk = await as_role("front_desk")
    response = await client.post("/housekeeping/rooms/room2/status", json={"state": "inspected"}, headers=desk)
    assert response.status_code == 200 and response.json()["clean_state"] == "inspected"


async def test_status_changes_check_the_room_and_the_value(client, as_role):
    keeper = await as_role("housekeeping")
    assert (await client.post("/housekeeping/rooms/nowhere/status", json={"state": "clean"}, headers=keeper)).status_code == 404
    assert (await client.post("/housekeeping/rooms/room1/status", json={"state": "shiny"}, headers=keeper)).status_code == 422


async def test_maintenance_cannot_use_the_housekeeping_screens(client, as_role):
    tech = await as_role("maintenance")
    assert (await client.get("/housekeeping/rooms", headers=tech)).status_code == 403
    assert (await client.post("/housekeeping/rooms/room1/status", json={"state": "clean"}, headers=tech)).status_code == 403


async def test_an_issue_goes_from_reported_to_resolved(client, as_role):
    keeper = await as_role("housekeeping")
    tech = await as_role("maintenance")

    created = await client.post(
        "/maintenance/issues",
        json={"room_id": "room3", "title": "Shower drain blocked", "details": "Water stays in the tray"},
        headers=keeper,
    )
    assert created.status_code == 201
    issue = created.json()
    assert issue["status"] == "open" and issue["reported_by"] == "Test housekeeping"

    # the housekeeping list shows the open issue against the room
    rooms = by_room((await client.get("/housekeeping/rooms", headers=keeper)).json())
    assert rooms["room3"]["open_issues"] == 1

    # housekeepers can report issues but not change them
    denied = await client.patch(f"/maintenance/issues/{issue['id']}", json={"status": "resolved"}, headers=keeper)
    assert denied.status_code == 403

    started = await client.patch(f"/maintenance/issues/{issue['id']}", json={"status": "in_progress"}, headers=tech)
    assert started.status_code == 200 and started.json()["updated_by"] == "Test maintenance"
    assert len((await client.get("/maintenance/issues", headers=tech)).json()) == 1

    done = await client.patch(f"/maintenance/issues/{issue['id']}", json={"status": "resolved"}, headers=tech)
    assert done.json()["status"] == "resolved" and done.json()["resolved_at"] is not None

    # resolved issues leave the default list but stay in "all"
    assert (await client.get("/maintenance/issues", headers=tech)).json() == []
    assert len((await client.get("/maintenance/issues?status=all", headers=tech)).json()) == 1
    rooms = by_room((await client.get("/housekeeping/rooms", headers=keeper)).json())
    assert rooms["room3"]["open_issues"] == 0

    reopened = await client.patch(f"/maintenance/issues/{issue['id']}", json={"status": "open"}, headers=tech)
    assert reopened.json()["resolved_at"] is None


async def test_issue_input_is_checked(client, as_role):
    tech = await as_role("maintenance")
    good = {"room_id": "room1", "title": "Light flickers"}
    assert (await client.post("/maintenance/issues", json={**good, "room_id": "nowhere"}, headers=tech)).status_code == 404
    assert (await client.post("/maintenance/issues", json={**good, "title": "x"}, headers=tech)).status_code == 422
    assert (await client.get("/maintenance/issues?status=sideways", headers=tech)).status_code == 422
    missing = await client.patch("/maintenance/issues/nope", json={"status": "resolved"}, headers=tech)
    assert missing.status_code == 404


async def test_guests_cannot_reach_staff_operations(client, session, make_booking):
    from server.auth import issue_guest_token

    booking = await make_booking()
    guest = {"Authorization": f"Bearer {await issue_guest_token(session, booking)}"}
    await session.commit()
    assert (await client.get("/housekeeping/rooms", headers=guest)).status_code == 403
    assert (await client.get("/maintenance/issues", headers=guest)).status_code == 403
    assert (await client.get("/housekeeping/rooms")).status_code == 401