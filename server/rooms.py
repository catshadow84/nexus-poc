"""Picking a free room for a new booking."""

import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Booking

DEFAULT_ASSIGNABLE = "room1,room2"  # the rooms that have (simulated) devices


def assignable_rooms() -> list[str]:
    """Rooms a new booking may be put in, in the order they are tried.

    Set ASSIGNABLE_ROOMS in .env (comma separated). The default is the two rooms
    the simulator runs, so a demo guest always lands in a room that responds.
    """
    raw = os.getenv("ASSIGNABLE_ROOMS", DEFAULT_ASSIGNABLE)
    return [r.strip() for r in raw.split(",") if r.strip()]


async def assign_room(
    session: AsyncSession, arrival: datetime, departure: datetime
) -> str | None:
    """The first room with no other stay overlapping these dates, or None."""
    result = await session.execute(
        select(Booking).where(Booking.status.in_(("RESERVED", "CHECKED_IN")))
    )
    busy: set[str] = set()
    for other in result.scalars():
        if other.planned_check_in is None or other.planned_check_out is None:
            # No dates on record: only a guest who is in the room blocks it.
            if other.status == "CHECKED_IN":
                busy.add(other.room_id)
            continue
        if other.planned_check_in < departure and other.planned_check_out > arrival:
            busy.add(other.room_id)
    for room in assignable_rooms():
        if room not in busy:
            return room
    return None
