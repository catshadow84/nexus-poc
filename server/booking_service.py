import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Booking, Guest
from .devices import registry
from .state import store
from .mqtt_bus import bus
from .broadcast import broadcaster


log = logging.getLogger("booking")


# statuses
RESERVED = "RESERVED"
CHECKED_IN = "CHECKED_IN"
CHECKED_OUT = "CHECKED_OUT"


# ---------- helpers ----------


async def _apply_preferences(guest: Guest) -> list[str]:
    """Send a command for each device in the guest's preferences.
    Returns list of device ids successfully commanded."""
    applied = []
    for device_id, value in (guest.preferences or {}).items():
        try:
            dev = registry.get(device_id)
            cmd = dev.make_command(value)
        except Exception as e:
            log.warning("skip pref %s: %s", device_id, e)
            continue

        store.set_desired(device_id, cmd.value, cmd.id)
        await bus.publish(f"{dev.topic_base}/command", cmd.model_dump(mode="json"))
        applied.append(device_id)

    await broadcaster.broadcast({"type": "state", "data": store.snapshot()})
    return applied


async def _reset_room() -> None:
    """Send default commands to every device."""
    defaults = {
        "light": {"power": "off", "brightness": 0, "color": "neutral"},
        "thermostat": {"target_c": 22.0, "mode": "cool"},
        "curtain": {"open_pct": 0},
    }
    for device_id, value in defaults.items():
        try:
            dev = registry.get(device_id)
            cmd = dev.make_command(value)
        except Exception as e:
            log.warning("skip reset %s: %s", device_id, e)
            continue
        store.set_desired(device_id, cmd.value, cmd.id)
        await bus.publish(f"{dev.topic_base}/command", cmd.model_dump(mode="json"))

    await broadcaster.broadcast({"type": "state", "data": store.snapshot()})


# ---------- public API ----------


async def get_guest(session: AsyncSession, guest_id: str) -> Guest | None:
    result = await session.execute(select(Guest).where(Guest.id == guest_id))
    return result.scalar_one_or_none()


async def get_booking(session: AsyncSession, booking_id: str) -> Booking | None:
    result = await session.execute(select(Booking).where(Booking.id == booking_id))
    return result.scalar_one_or_none()


async def check_in(session: AsyncSession, booking: Booking) -> dict:
    if booking.status == CHECKED_IN:
        raise ValueError("Booking already checked in")
    if booking.status == CHECKED_OUT:
        raise ValueError("Cannot re-check-in a completed booking")
    # guard: room must be free
    occupied = await session.execute(
        select(Booking)
        .where(Booking.room_id == booking.room_id)
        .where(Booking.status == CHECKED_IN)
        .where(Booking.id != booking.id)
    )
    if occupied.scalars().first():
        raise ValueError(f"Room {booking.room_id} is occupied")
    booking.status = CHECKED_IN
    booking.actual_check_in = datetime.utcnow()

    guest = await get_guest(session, booking.guest_id)
    applied = await _apply_preferences(guest) if guest else []

    await session.commit()
    return {"applied_devices": applied}


async def check_out(session: AsyncSession, booking: Booking) -> dict:
    if booking.status != CHECKED_IN:
        raise ValueError("Booking is not checked in")

    booking.status = CHECKED_OUT
    booking.actual_check_out = datetime.utcnow()
    await _reset_room()
    await session.commit()
    return {"reset": True}