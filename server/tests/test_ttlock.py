from datetime import datetime

import httpx
import pytest

from server import ttlock
from server.ttlock import SimulatedTTLock, TTLockClient, TTLockError, generate_pin, to_ms


@pytest.fixture(autouse=True)
def ttlock_env(monkeypatch):
    for name in ("TTLOCK_CLIENT_ID", "TTLOCK_CLIENT_SECRET", "TTLOCK_USERNAME", "TTLOCK_PASSWORD_MD5", "TTLOCK_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TTLOCK_API_BASE", "https://ttlock.test")
    ttlock.reset_ttlock()
    yield
    ttlock.reset_ttlock()


def set_credentials(monkeypatch):
    monkeypatch.setenv("TTLOCK_CLIENT_ID", "cid")
    monkeypatch.setenv("TTLOCK_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("TTLOCK_USERNAME", "owner")
    monkeypatch.setenv("TTLOCK_PASSWORD_MD5", "a" * 32)


def fake_api(monkeypatch, responses):
    """A client wired to a fake TT Lock. Returns (client, list of requests seen)."""
    set_credentials(monkeypatch)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(httpx.QueryParams(request.content.decode()))))
        return httpx.Response(200, json=responses[request.url.path])

    return TTLockClient(transport=httpx.MockTransport(handler)), seen


TOKEN = {"access_token": "tok123", "uid": 7, "expires_in": 7776000}


def test_pins_have_six_digits_and_are_never_trivial():
    for _ in range(500):
        pin = generate_pin()
        assert len(pin) == 6 and pin.isdigit()
        assert pin[0] != "0"
        assert len(set(pin)) > 1
        assert pin not in ("123456", "234567", "345678", "456789", "987654", "876543", "765432", "654321")


def test_to_ms_treats_naive_datetimes_as_utc():
    assert to_ms(datetime(1970, 1, 1, 0, 0, 1)) == 1000


async def test_unlock_logs_in_once_and_sends_the_right_fields(monkeypatch):
    client, seen = fake_api(monkeypatch, {"/oauth2/token": TOKEN, "/v3/lock/unlock": {"errcode": 0}})
    await client.unlock(24451)
    await client.unlock(24451)

    paths = [path for path, _ in seen]
    assert paths == ["/oauth2/token", "/v3/lock/unlock", "/v3/lock/unlock"]
    login = seen[0][1]
    assert login["client_id"] == "cid" and login["username"] == "owner" and login["password"] == "a" * 32
    unlock = seen[1][1]
    assert unlock["clientId"] == "cid" and unlock["accessToken"] == "tok123"
    assert unlock["lockId"] == "24451" and unlock["date"].isdigit()


async def test_remote_unlock_off_gives_a_helpful_error(monkeypatch):
    client, _ = fake_api(
        monkeypatch,
        {"/oauth2/token": TOKEN, "/v3/lock/unlock": {"errcode": -4043, "errmsg": "not supported"}},
    )
    with pytest.raises(TTLockError, match="Remote unlock is off") as info:
        await client.unlock(1)
    assert info.value.errcode == -4043


async def test_add_passcode_sends_a_period_pin_through_the_gateway(monkeypatch):
    client, seen = fake_api(
        monkeypatch, {"/oauth2/token": TOKEN, "/v3/keyboardPwd/add": {"keyboardPwdId": 24242}}
    )
    start, end = datetime(2026, 12, 1, 14, 0), datetime(2026, 12, 3, 12, 0)
    passcode_id = await client.add_passcode(24451, "482915", "NEXUS abc12345", start, end)

    assert passcode_id == 24242
    sent = seen[1][1]
    assert sent["keyboardPwd"] == "482915"
    assert sent["keyboardPwdType"] == "3" and sent["addType"] == "2"
    assert sent["startDate"] == str(to_ms(start)) and sent["endDate"] == str(to_ms(end))


async def test_bad_login_is_reported_without_the_secret(monkeypatch):
    client, _ = fake_api(monkeypatch, {"/oauth2/token": {"errcode": 10003, "errmsg": "invalid client"}})
    with pytest.raises(TTLockError) as info:
        await client.login()
    assert "csecret" not in str(info.value)


def test_client_without_credentials_names_the_missing_settings():
    with pytest.raises(TTLockError, match="TTLOCK_CLIENT_ID"):
        TTLockClient()


async def test_without_credentials_the_simulated_door_is_used():
    lock = ttlock.get_ttlock()
    assert isinstance(lock, SimulatedTTLock)
    await lock.unlock(5)
    passcode_id = await lock.add_passcode(5, "482915", "x", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert lock.unlocks == [5]
    assert lock.passcodes[passcode_id]["pin"] == "482915"


def test_credentials_switch_on_the_live_client_unless_sim_is_forced(monkeypatch):
    set_credentials(monkeypatch)
    assert ttlock.get_ttlock().mode == "live"
    ttlock.reset_ttlock()
    monkeypatch.setenv("TTLOCK_MODE", "sim")
    assert ttlock.get_ttlock().mode == "sim"