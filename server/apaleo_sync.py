import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .apaleo import ApaleoClient
from .booking_service import CANCELED, NO_SHOW, RESERVED, CHECKED_OUT, _reset_room
from .models import Booking

log = logging.getLogger("apaleo_sync")


def reconcile(booking, reservation: dict) -> list[str]:
    changes: list[str] = []

    status = reservation.get("status")
    
    # 1. Handle Checked Out (Energy Scene)
    if status == "CheckedOut":
        if booking.status != CHECKED_OUT:
            booking.status = CHECKED_OUT
            changes.append("status -> CHECKED_OUT")
            
    # 2. Handle Canceled / NoShow
    elif status in ("Canceled", "NoShow"):
        new_status = CANCELED if status == "Canceled" else NO_SHOW
        if booking.status == RESERVED:
            booking.status = new_status
            changes.append(f"status -> {new_status}")
        elif booking.status != new_status:
            log.warning("Apaleo says %s but local booking is %s", status, booking.status)

    # 3. Handle Date changes
    if booking.status == RESERVED:
        for field, key in (("planned_check_in", "arrival"), ("planned_check_out", "departure")):
            value = reservation.get(key)
            if not isinstance(value, str) or len(value) < 10:
                continue
            try:
                day = date.fromisoformat(value[:10])
            except ValueError:
                continue
            new_value = datetime.combine(day, time.min)
            if getattr(booking, field) != new_value:
                setattr(booking, field, new_value)
                changes.append(f"{field} -> {day.isoformat()}")

    return changes


async def process_event(session: AsyncSession, client: ApaleoClient, payload: dict) -> str:
    if str(payload.get("topic", "")).lower() != "reservation":
        return "ignored topic"

    entity_id = (payload.get("data") or {}).get("entityId") or payload.get("entityId")
    if not entity_id:
        return "no entity id"

    result = await session.execute(
        select(Booking).where(Booking.apaleo_reservation_id == entity_id)
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        return f"{entity_id} is not one of ours"

    reservation = await client.get(f"/booking/v1/reservations/{entity_id}")
    log.info(
        "reservation %s: status=%s arrival=%s departure=%s",
        entity_id, reservation.get("status"),
        reservation.get("arrival"), reservation.get("departure"),
    )
    
    changes = reconcile(booking, reservation)
    
    # If the guest checked out in Apaleo, trigger the energy saving scene
    if "status -> CHECKED_OUT" in changes:
        log.info("Triggering Energy Scene for room %s", booking.room_id)
        await _reset_room(booking.room_id)
        changes.append("room reset triggered")

    return f"{entity_id}: " + ("; ".join(changes) if changes else "no changes")