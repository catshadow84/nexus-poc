import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .booking_service import CHECKED_IN, get_booking
from .db import get_session
from .models import AccessToken, Booking
from .timeutil import utcnow

TOKEN_LIFETIME = timedelta(days=30)
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Who is calling: staff, or a guest tied to one booking."""

    is_staff: bool
    booking_id: str | None = None
    guest_id: str | None = None


def auth_disabled() -> bool:
    """Development escape hatch. Never enable on a reachable server."""
    return os.getenv("AUTH_DISABLED") == "1"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


async def issue_guest_token(session: AsyncSession, booking: Booking) -> str:
    """Create a token for a booking and revoke its older ones. The caller commits."""
    await session.flush()  # makes sure a new booking already has its id
    await session.execute(
        update(AccessToken)
        .where(AccessToken.booking_id == booking.id)
        .where(AccessToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    token = secrets.token_urlsafe(32)
    session.add(
        AccessToken(
            token_hash=hash_token(token),
            booking_id=booking.id,
            expires_at=utcnow() + TOKEN_LIFETIME,
        )
    )
    return token


async def principal_from_token(session: AsyncSession, token: str) -> Principal:
    staff_key = os.getenv("STAFF_API_KEY", "")
    if staff_key and secrets.compare_digest(token.encode(), staff_key.encode()):
        return Principal(is_staff=True)

    result = await session.execute(
        select(AccessToken, Booking)
        .join(Booking, Booking.id == AccessToken.booking_id)
        .where(AccessToken.token_hash == hash_token(token))
    )
    row = result.first()
    if row is None:
        raise _unauthorized("Invalid token")
    access, booking = row
    if access.revoked_at is not None or access.expires_at < utcnow():
        raise _unauthorized("Token expired or revoked")
    return Principal(is_staff=False, booking_id=booking.id, guest_id=booking.guest_id)


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if auth_disabled():
        return Principal(is_staff=True)
    if credentials is None:
        raise _unauthorized("Missing token")
    return await principal_from_token(session, credentials.credentials)


async def optional_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal | None:
    if auth_disabled():
        return Principal(is_staff=True)
    if credentials is None:
        return None
    try:
        return await principal_from_token(session, credentials.credentials)
    except HTTPException:
        return None


async def require_staff(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_staff:
        raise HTTPException(403, "Staff only")
    return principal


async def owned_booking(
    booking_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """The booking, if the caller may see it. Anything else is a plain 404."""
    booking = await get_booking(session, booking_id)
    if booking is None or not (principal.is_staff or principal.booking_id == booking.id):
        raise HTTPException(404, "booking not found")
    return booking


async def can_access_room(
    session: AsyncSession, principal: Principal, room_id: str
) -> bool:
    if principal.is_staff:
        return True
    if not principal.booking_id:
        return False
    booking = await get_booking(session, principal.booking_id)
    return bool(booking and booking.room_id == room_id and booking.status == CHECKED_IN)


async def room_access(
    room_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> str:
    if not await can_access_room(session, principal, room_id):
        raise HTTPException(403, "No access to this room")
    return room_id