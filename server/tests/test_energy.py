from datetime import timedelta

import pytest

from server.booking_service import CHECKED_OUT, check_in, check_out
from server.energy import energy_report, vacant_hours
from server.passwords import reset_throttle
from server.staff import create_staff
from server.timeutil import utcnow

PASSWORD = "a long enough password"
NOW = utcnow().replace(microsecond=0)


@pytest.fixture(autouse=True)
def energy_env(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    for name in ("AC_OCCUPIED_KW", "AC_ECO_KW", "ENERGY_PRICE_PER_KWH", "ENERGY_CURRENCY",
                 "GRID_KG_CO2_PER_KWH", "ENERGY_CAP_HOURS", "HOTEL_ROOMS"):
        monkeypatch.delenv(name, raising=False)
    reset_throttle()
    yield
    reset_throttle()


def h(n):
    return timedelta(hours=n)


def test_a_stretch_ends_at_the_next_check_in():
    stays = [(NOW - h(30), NOW - h(20)), (NOW - h(10), None)]
    assert vacant_hours(stays, NOW, 72) == [10.0]


def test_a_stretch_without_a_next_guest_runs_until_now():
    assert vacant_hours([(NOW - h(30), NOW - h(6))], NOW, 72) == [6.0]


def test_a_guest_still_in_the_room_saves_nothing():
    assert vacant_hours([(NOW - h(5), None)], NOW, 72) == []


def test_one_stretch_is_capped():
    assert vacant_hours([(NOW - h(500), NOW - h(400))], NOW, 72) == [72.0]


def test_stays_are_sorted_before_pairing():
    stays = [(NOW - h(10), None), (NOW - h(30), NOW - h(20))]
    assert vacant_hours(stays, NOW, 72) == [10.0]


async def test_the_report_counts_energy_for_a_checked_out_room(session, make_booking):
    booking = await make_booking(room_id="room1")
    await check_in(session, booking)
    await check_out(session, booking)
    booking.actual_check_in = NOW - h(30)
    booking.actual_check_out = NOW - h(10)
    await session.commit()

    report = await energy_report(session, now=NOW)
    room1 = {r["room_id"]: r for r in report["rooms"]}["room1"]
    assert room1["checkouts"] == 1
    assert room1["vacant_hours"] == 10.0
    assert room1["kwh_saved"] == 9.0  # 10 h x (1.2 - 0.3) kW
    assert room1["money_saved"] == 1.8  # 9 kWh x 0.20
    assert room1["co2_kg_saved"] == 4.5  # 9 kWh x 0.5
    assert report["totals"]["kwh_saved"] == 9.0
    assert report["estimated"] is True
    assert report["currency"] == "USD"


async def test_settings_come_from_the_environment(session, make_booking, monkeypatch):
    monkeypatch.setenv("AC_OCCUPIED_KW", "2.3")
    monkeypatch.setenv("ENERGY_PRICE_PER_KWH", "0.5")
    monkeypatch.setenv("ENERGY_CURRENCY", "eur")
    booking = await make_booking(room_id="room2")
    booking.status = CHECKED_OUT
    booking.actual_check_in = NOW - h(12)
    booking.actual_check_out = NOW - h(5)
    await session.commit()

    report = await energy_report(session, now=NOW)
    room2 = {r["room_id"]: r for r in report["rooms"]}["room2"]
    assert room2["kwh_saved"] == 10.0  # 5 h x (2.3 - 0.3)
    assert room2["money_saved"] == 5.0
    assert report["currency"] == "EUR"


async def test_a_bad_number_in_the_environment_falls_back(session, monkeypatch):
    monkeypatch.setenv("AC_ECO_KW", "lots")
    report = await energy_report(session, now=NOW)
    assert report["assumptions"]["eco_kw"] == 0.3


async def test_an_empty_hotel_reports_zeros(session):
    report = await energy_report(session, now=NOW)
    assert report["totals"]["kwh_saved"] == 0
    assert report["totals"]["checkouts"] == 0


async def login(client, session, role):
    await create_staff(session, f"{role}-user".replace("_", "-"), f"Test {role}", role, PASSWORD)
    response = await client.post(
        "/staff/login", json={"username": f"{role}-user".replace("_", "-"), "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_only_managers_see_the_energy_report(client, session):
    assert (await client.get("/energy")).status_code in (401, 403)
    front = await login(client, session, "front_desk")
    assert (await client.get("/energy", headers=front)).status_code == 403
    manager = await login(client, session, "manager")
    response = await client.get("/energy", headers=manager)
    assert response.status_code == 200
    assert "totals" in response.json()
