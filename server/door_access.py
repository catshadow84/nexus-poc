"""The guest's door code: written to the lock at check-in, removed at check-out.

Uses TT Lock (or the simulated door when TT Lock is not set up). A failure here
never stops a check-in: the guest can still use the Unlock button, and the front
desk sees that no code was made.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Booking
from .timeutil import utcnow
from .ttlock import TTLockError, generate_pin, get_ttlock

log = logging.getLogger("door_access")

SIM_LOCK_BASE = 900000  # fake lock ids for the simulated door


def lock_id_for(room_id: str) -> int | None:
    """The TT Lock id of a room's door.

    TTLOCK_LOCK_IDS in .env maps rooms to lock ids: room1:1234567,room2:7654321.
    With the simulated door every room has a made-up lock id.
    """
    for pair in os.getenv("TTLOCK_LOCK_IDS", "").split(","):
        room, _, lock = pair.partition(":")
        if room.strip() == room_id and lock.strip().isdigit():
            return int(lock.strip())
    if get_ttlock().mode == "sim":
        digits = re.sub(r"\D", "", room_id)
        return SIM_LOCK_BASE + (int(digits) if digits else 0)
    return None


def hotel_tz():
    """The hotel's time zone (HOTEL_TIMEZONE, for example Asia/Beirut); UTC if unset or unknown."""
    name = os.getenv("HOTEL_TIMEZONE", "").strip()
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # On Windows this needs the "tzdata" package: pip install tzdata
        log.warning("Unknown time zone %r, using UTC. On Windows run: pip install tzdata", name)
        return timezone.utc


def pin_window(booking: Booking):
    """(start, end) for the code, as naive UTC."""
    start = utcnow().replace(second=0, microsecond=0)
    hour = int(os.getenv("CHECKOUT_HOUR", "12"))
    if booking.planned_check_out:
        # Check-out time on the departure day, in the hotel's own time zone.
        local_end = datetime.combine(
            booking.planned_check_out.date(), dtime(hour, 0), tzinfo=hotel_tz()
        )
        end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        end = start + timedelta(hours=24)
    if end < start + timedelta(hours=2):
        end = start + timedelta(hours=2)
    return start, end


async def issue_door_pin(booking: Booking) -> dict:
    """Make a code for this booking. Never raises. Sets the booking's door_pin fields."""
    lock_id = lock_id_for(booking.room_id)
    if lock_id is None:
        return {
            "door_pin_issued": False,
            "door_pin_error": f"No lock is set up for {booking.room_id}",
        }
    start, end = pin_window(booking)
    pin = generate_pin()
    try:
        passcode_id = await get_ttlock().add_passcode(
            lock_id, pin, f"Stay {booking.id[:8]}", start, end
        )
    except TTLockError as e:
        log.error("Door code for booking %s failed: %s", booking.id, e)
        return {"door_pin_issued": False, "door_pin_error": str(e)}
    booking.door_pin = pin
    booking.door_pin_id = passcode_id
    booking.door_pin_expires = end
    return {"door_pin_issued": True, "door_pin_error": None}


async def revoke_door_pin(booking: Booking) -> None:
    """Remove the code from the lock and from the booking. Never raises."""
    if booking.door_pin_id is not None:
        lock_id = lock_id_for(booking.room_id)
        if lock_id is not None:
            try:
                await get_ttlock().delete_passcode(lock_id, booking.door_pin_id)
            except TTLockError as e:
                # The code still stops working at its end time.
                log.error("Could not remove door code of booking %s: %s", booking.id, e)
    booking.door_pin = None
    booking.door_pin_id = None
    booking.door_pin_expires = None
