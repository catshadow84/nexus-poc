"""Password hashing and a simple login throttle. Standard library only.

Passwords are never stored. We store a salted scrypt hash, written as
    scrypt$N$r$p$salt(hex)$hash(hex)
so the settings can change later and old hashes still verify.
"""

import hashlib
import hmac
import secrets
import time

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSWORD_LENGTH = 10


def check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 200:
        raise ValueError("Password is too long")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(hash_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# Checked when the username does not exist, so a wrong username takes as long
# as a wrong password and the response time does not reveal which names exist.
DUMMY_HASH = hash_password("not-a-real-password")


# ---------- login throttle (kept in memory; resets when the server restarts) ----------

MAX_FAILURES = 5
WINDOW_SECONDS = 300
_failures: dict[str, list[float]] = {}


def _recent(key: str) -> list[float]:
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
    _failures[key] = recent
    return recent


def is_locked(key: str) -> bool:
    return len(_recent(key)) >= MAX_FAILURES


def note_failure(key: str) -> None:
    _recent(key).append(time.time())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)


def reset_throttle() -> None:
    _failures.clear()