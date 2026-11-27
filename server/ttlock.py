"""TT Lock Open Platform client, plus a simulated door for development.

Docs: https://euopen.ttlock.com/ (Cloud API V3)

Two things can happen on a lock from here:
  * unlock(lock_id)        -> remote unlock through the gateway
  * add_passcode(...)      -> a custom PIN that is only valid between two times

Without TT Lock credentials in .env (or with TTLOCK_MODE=sim) every call goes to
SimulatedTTLock, so the app and the tests work with no hardware.
"""

import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = logging.getLogger("ttlock")

DEFAULT_API_BASE = "https://euapi.ttlock.com"

# Error codes taken from the TT Lock docs.
ERROR_HINTS = {
    -4043: "Remote unlock is off for this lock. Switch it on in the TTLock app's lock settings.",
    -3009: "The lock's passcode memory is full. Delete old passcodes first.",
}


class TTLockError(Exception):
    def __init__(self, message: str, errcode: int | None = None) -> None:
        super().__init__(message)
        self.errcode = errcode


def to_ms(moment: datetime) -> int:
    """Naive UTC datetime (what the rest of the app uses) -> milliseconds."""
    return int(moment.replace(tzinfo=timezone.utc).timestamp() * 1000)


def generate_pin(length: int = 6) -> str:
    """A random numeric PIN that is not trivial.

    The first digit is never 0, because the API takes the passcode as a number
    and would drop a leading zero. All-same digits (111111) and straight runs
    (123456, 654321) are rejected.
    """
    while True:
        pin = secrets.choice("123456789") + "".join(
            secrets.choice("0123456789") for _ in range(length - 1)
        )
        steps = {int(b) - int(a) for a, b in zip(pin, pin[1:])}
        if len(set(pin)) == 1 or steps in ({1}, {-1}):
            continue
        return pin


class TTLockClient:
    mode = "live"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base = os.getenv("TTLOCK_API_BASE", DEFAULT_API_BASE).rstrip("/")
        self.client_id = os.getenv("TTLOCK_CLIENT_ID", "")
        self.client_secret = os.getenv("TTLOCK_CLIENT_SECRET", "")
        self.username = os.getenv("TTLOCK_USERNAME", "")
        self.password_md5 = os.getenv("TTLOCK_PASSWORD_MD5", "")
        missing = [
            name
            for name, value in (
                ("TTLOCK_CLIENT_ID", self.client_id),
                ("TTLOCK_CLIENT_SECRET", self.client_secret),
                ("TTLOCK_USERNAME", self.username),
                ("TTLOCK_PASSWORD_MD5", self.password_md5),
            )
            if not value
        ]
        if missing:
            raise TTLockError("Set these in .env: " + ", ".join(missing))
        self._transport = transport
        self._token: str | None = None
        self._expires_at = 0.0
        self._uid: int | None = None

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20, transport=self._transport)

    async def login(self) -> dict:
        """Get (or reuse) the access token. Returns {"uid", "expires_in"}."""
        if self._token and time.time() < self._expires_at - 3600:
            return {"uid": self._uid, "expires_in": int(self._expires_at - time.time())}
        try:
            async with self._http() as http:
                resp = await http.post(
                    f"{self.base}/oauth2/token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "username": self.username,
                        "password": self.password_md5,
                    },
                )
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TTLockError(f"Could not reach TT Lock: {e}") from e
        if "access_token" not in data:
            # Never echo the request; it holds the secret.
            raise TTLockError(
                f"TT Lock login failed: {data.get('errmsg') or data.get('error_description') or 'no reason given'}",
                data.get("errcode"),
            )
        self._token = data["access_token"]
        self._uid = data.get("uid")
        self._expires_at = time.time() + int(data.get("expires_in", 0))
        return {"uid": self._uid, "expires_in": int(data.get("expires_in", 0))}

    async def _post(self, path: str, fields: dict) -> dict:
        await self.login()
        body = {
            "clientId": self.client_id,
            "accessToken": self._token,
            "date": int(time.time() * 1000),
            **fields,
        }
        try:
            async with self._http() as http:
                resp = await http.post(self.base + path, data=body)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TTLockError(f"Could not reach TT Lock: {e}") from e
        # The HTTP status is often 200 even on failure, so look at errcode.
        code = data.get("errcode", 0)
        if code != 0:
            hint = ERROR_HINTS.get(code, data.get("errmsg", "unknown error"))
            raise TTLockError(f"TT Lock error {code}: {hint}", code)
        return data

    async def unlock(self, lock_id: int) -> None:
        await self._post("/v3/lock/unlock", {"lockId": lock_id})

    async def add_passcode(
        self, lock_id: int, pin: str, name: str, start: datetime, end: datetime
    ) -> int:
        """Write a PIN that works from `start` to `end` (naive UTC). Needs the gateway."""
        data = await self._post(
            "/v3/keyboardPwd/add",
            {
                "lockId": lock_id,
                "keyboardPwd": pin,
                "keyboardPwdName": name,
                "keyboardPwdType": 3,  # 3 = valid for a period
                "startDate": to_ms(start),
                "endDate": to_ms(end),
                "addType": 2,  # 2 = write through the gateway
            },
        )
        if "keyboardPwdId" not in data:
            raise TTLockError(f"TT Lock did not return a passcode id: {data}")
        return int(data["keyboardPwdId"])

    async def delete_passcode(self, lock_id: int, passcode_id: int) -> None:
        """Remove a PIN from the lock, through the gateway.

        The endpoint and fields follow the TT Lock docs as I remember them
        (/v3/keyboardPwd/delete, deleteType 2 = gateway). Check this against the
        "Delete passcode" page before relying on it with a real lock.
        """
        await self._post(
            "/v3/keyboardPwd/delete",
            {"lockId": lock_id, "keyboardPwdId": passcode_id, "deleteType": 2},
        )


class SimulatedTTLock:
    """Same methods as TTLockClient, but nothing leaves this computer."""

    mode = "sim"

    def __init__(self) -> None:
        self.unlocks: list[int] = []
        self.passcodes: dict[int, dict] = {}
        self._next_id = 1

    async def login(self) -> dict:
        return {"uid": 0, "expires_in": 0}

    async def unlock(self, lock_id: int) -> None:
        self.unlocks.append(lock_id)

    async def add_passcode(
        self, lock_id: int, pin: str, name: str, start: datetime, end: datetime
    ) -> int:
        passcode_id = self._next_id
        self._next_id += 1
        self.passcodes[passcode_id] = {
            "lock_id": lock_id,
            "pin": pin,
            "name": name,
            "start": start,
            "end": end,
        }
        return passcode_id

    async def delete_passcode(self, lock_id: int, passcode_id: int) -> None:
        self.passcodes.pop(passcode_id, None)


_instance: TTLockClient | SimulatedTTLock | None = None


def get_ttlock() -> TTLockClient | SimulatedTTLock:
    """The live client if .env is complete, otherwise the simulated one."""
    global _instance
    if _instance is None:
        if os.getenv("TTLOCK_MODE", "").lower() == "sim":
            _instance = SimulatedTTLock()
        else:
            try:
                _instance = TTLockClient()
            except TTLockError as e:
                log.warning("TT Lock not configured, using the simulated door. %s", e)
                _instance = SimulatedTTLock()
        log.info("TT Lock mode: %s", _instance.mode)
    return _instance


def reset_ttlock() -> None:
    """Forget the cached client (used by tests)."""
    global _instance
    _instance = None