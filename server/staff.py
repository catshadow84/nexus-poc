"""Staff accounts: creating them, checking logins, issuing session tokens."""

import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import hash_token
from .models import StaffToken, StaffUser
from .passwords import (
    DUMMY_HASH,
    check_password_rules,
    hash_password,
    note_failure,
    verify_password,
)
from .timeutil import utcnow

ROLES = ("front_desk", "housekeeping", "maintenance", "manager")
STAFF_TOKEN_LIFETIME = timedelta(hours=12)
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def clean_username(username: str) -> str:
    return username.strip().lower()


async def get_staff_by_username(session: AsyncSession, username: str) -> StaffUser | None:
    result = await session.execute(
        select(StaffUser).where(StaffUser.username == clean_username(username))
    )
    return result.scalar_one_or_none()


async def create_staff(
    session: AsyncSession, username: str, name: str, role: str, password: str
) -> StaffUser:
    username = clean_username(username)
    if not USERNAME_RE.match(username):
        raise ValueError("Username must be 3-32 characters: letters, digits, dot, dash or underscore")
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
    if not name.strip():
        raise ValueError("Name is required")
    check_password_rules(password)
    if await get_staff_by_username(session, username):
        raise ValueError("That username is already taken")

    user = StaffUser(
        username=username,
        name=name.strip(),
        role=role,
        password_hash=hash_password(password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ValueError("That username is already taken")
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> StaffUser | None:
    """The account if the login is right and the account is active, else None."""
    user = await get_staff_by_username(session, username)
    # Always do one password check, so timing does not show whether the name exists.
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok or not user.active:
        note_failure(clean_username(username))
        return None
    return user


async def issue_staff_token(session: AsyncSession, user: StaffUser) -> tuple[str, datetime]:
    """Create a session token. Only its hash is stored. The caller commits."""
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + STAFF_TOKEN_LIFETIME
    session.add(
        StaffToken(token_hash=hash_token(token), staff_id=user.id, expires_at=expires_at)
    )
    await session.flush()
    return token, expires_at