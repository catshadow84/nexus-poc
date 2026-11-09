import pytest
from pydantic import ValidationError

from server.booking_service import check_in, check_out
from server.schemas import BoseValue, CentralAcValue

STAFF_KEY = "test-staff-key-0123456789-0123456789"
STAFF = {"Authorization": f"Bearer {STAFF_KEY}"}


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("STAFF_API_KEY", STAFF_KEY)
    monkeypatch.delenv("AUTH_DISABLED", raising=False)


def commands_by_topic(published):
    return {topic: payload["value"] for topic, payload in published}


def test_central_ac_accepts_eco_and_rejects_nonsense():
    assert CentralAcValue(target_c=26, mode="eco").mode == "eco"
    with pytest.raises(ValidationError):
        CentralAcValue(target_c=22, mode="turbo")


def test_bose_volume_must_be_between_0_and_100():
    assert BoseValue(power="on", volume=100).volume == 100
    with pytest.raises(ValidationError):
        BoseValue(power="on", volume=101)


async def test_old_thermostat_preferences_still_apply(session, make_booking, published):
    booking = await make_booking(preferences={"thermostat": {"target_c": 20, "mode": "cool"}})
    result = await check_in(session, booking)
    assert result["applied_devices"] == ["central_ac"]
    assert commands_by_topic(published) == {
        "nexus/room1/central_ac/command": {"target_c": 20.0, "mode": "cool"}
    }


async def test_check_out_sets_eco_and_switches_the_speaker_off(session, make_booking, published):
    booking = await make_booking()
    await check_in(session, booking)
    published.clear()
    await check_out(session, booking)
    sent = commands_by_topic(published)
    assert sent["nexus/room1/central_ac/command"]["mode"] == "eco"
    assert sent["nexus/room1/bose/command"]["power"] == "off"


async def test_staff_can_command_the_bose(client):
    response = await client.post(
        "/rooms/room1/device/bose/command",
        json={"power": "on", "volume": 30, "playing": True},
        headers=STAFF,
    )
    assert response.status_code == 200
    assert response.json()["topic"] == "nexus/room1/bose/command"


async def test_the_old_thermostat_device_no_longer_exists(client):
    response = await client.post(
        "/rooms/room1/device/thermostat/command",
        json={"target_c": 22, "mode": "cool"},
        headers=STAFF,
    )
    assert response.status_code == 404