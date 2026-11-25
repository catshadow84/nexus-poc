"""Housekeeping and maintenance logic shared by the booking flow and the routes."""

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Booking, RoomStatus
from .timeutil import utcnow

CLEAN_STATES = ("dirty", "cleaning", "clean", "inspected")
ISSUE_STATES = ("open", "in_progress", "resolved")
DEFAULT_ROOMS = "room1,room2,room3,room4,room5,room6"


def hotel_rooms() -> list[str]:
    """The rooms of the hotel. Set HOTEL_ROOMS in .env (comma separated) to change them."""
    raw = os.getenv("HOTEL_ROOMS", DEFAULT_ROOMS)
    return [r.strip() for r in raw.split(",") if r.strip()]


async def known_rooms(session: AsyncSession) -> set[str]:
    """Configured rooms plus any room that already has a status or a booking."""
    rooms = set(hotel_rooms())
    rooms.update((await session.execute(select(RoomStatus.room_id))).scalars())
    rooms.update((await session.execute(select(Booking.room_id).distinct())).scalars())
    return rooms


async def set_room_state(
    session: AsyncSession, room_id: str, state: str, by: str | None
) -> RoomStatus:
    """Create or update a room's cleaning state. The caller commits."""
    row = await session.get(RoomStatus, room_id)
    if row is None:
        row = RoomStatus(room_id=room_id)
        session.add(row)
    row.clean_state = state
    row.updated_at = utcnow()
    row.updated_by = by
    return row


async def mark_room_dirty(session: AsyncSession, room_id: str) -> None:
    """Called at check-out: the room now needs cleaning."""
    await set_room_state(session, room_id, "dirty", "check-out")