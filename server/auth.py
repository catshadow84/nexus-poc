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
from .models import AccessToken, Booking, StaffToken, StaffUser
from .timeutil import utcnow

TOKEN_LIFETIME = timedelta(days=30)
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Who is calling: staff, or a guest tied to one booking."""

    is_staff: bool
    booking_id: str | None = None
    guest_id: str | None = None
    role: str | None = None  # staff only: front_desk, housekeeping, maintenance, manager
    staff_id: str | None = None  # staff with their own account


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
        return Principal(is_staff=True, role="manager")  # the old shared key

    staff_row = (
        await session.execute(
            select(StaffToken, StaffUser)
            .join(StaffUser, StaffUser.id == StaffToken.staff_id)
            .where(StaffToken.token_hash == hash_token(token))
        )
    ).first()
    if staff_row is not None:
        staff_token, user = staff_row
        if staff_token.revoked_at is not None or staff_token.expires_at < utcnow() or not user.active:
            raise _unauthorized("Token expired or revoked")
        return Principal(is_staff=True, role=user.role, staff_id=user.id)

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
        return Principal(is_staff=True, role="manager")
    if credentials is None:
        raise _unauthorized("Missing token")
    return await principal_from_token(session, credentials.credentials)


async def optional_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal | None:
    if auth_disabled():
        return Principal(is_staff=True, role="manager")
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


def has_role(principal: Principal, *roles: str) -> bool:
    """True for staff with one of these roles. Managers pass every check."""
    return principal.is_staff and (principal.role == "manager" or principal.role in roles)


def require_role(*roles: str):
    """Staff with one of these roles. Managers can always do everything."""

    async def dependency(principal: Principal = Depends(require_staff)) -> Principal:
        if not has_role(principal, *roles):
            raise HTTPException(403, "Your role cannot do this")
        return principal

    return dependency


async def owned_booking(
    booking_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Booking:
    """The booking, if the caller may see it. Anything else is a plain 404."""
    booking = await get_booking(session, booking_id)
    if booking is None or not (has_role(principal, "front_desk") or principal.booking_id == booking.id):
        raise HTTPException(404, "booking not found")
    return booking


async def can_access_room(
    session: AsyncSession, principal: Principal, room_id: str
) -> bool:
    if principal.is_staff:
        # Housekeeping does not control devices.
        return has_role(principal, "front_desk", "maintenance")
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