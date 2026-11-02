import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .apaleo import ApaleoClient
from .booking_service import CANCELED, NO_SHOW, RESERVED
from .models import Booking

log = logging.getLogger("apaleo_sync")


def reconcile(booking, reservation: dict) -> list[str]:
    """Update our booking from Apaleo's version of the reservation.

    Returns a description of each change made. Unknown shapes are ignored.
    """
    changes: list[str] = []

    status = reservation.get("status")
    if status in ("Canceled", "NoShow"):
        new_status = CANCELED if status == "Canceled" else NO_SHOW
        if booking.status == RESERVED:
            booking.status = new_status
            changes.append(f"status -> {new_status}")
        elif booking.status != new_status:
            # The guest is already in the room or has left: a human must decide.
            log.warning("Apaleo says %s but local booking is %s", status, booking.status)

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
    """Handle one webhook event. Returns a short result for the log."""
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

    # Never trust the webhook body: ask Apaleo for the current truth.
    reservation = await client.get(f"/booking/v1/reservations/{entity_id}")
    log.info(
        "reservation %s: status=%s arrival=%s departure=%s",
        entity_id, reservation.get("status"),
        reservation.get("arrival"), reservation.get("departure"),
    )
    changes = reconcile(booking, reservation)
    return f"{entity_id}: " + ("; ".join(changes) if changes else "no changes")