"""Make the energy report show numbers right away, for a demo.

    python -m server.demo_backdate [hours]

Moves the most recent checked-out stay back in time so that the room has been
empty for [hours] hours (default 10). It only changes the check-in and check-out
times of that one booking. Never use it on real data.
"""

import asyncio
import sys
from datetime import timedelta

from sqlalchemy import select

from .db import SessionLocal
from .models import Booking
from .timeutil import utcnow


async def main(hours: float) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Booking)
            .where(Booking.status == "CHECKED_OUT", Booking.actual_check_out.is_not(None))
            .order_by(Booking.actual_check_out.desc())
            .limit(1)
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            print("No checked-out stay found. Check a guest in and out in the app first.")
            return
        stay = booking.actual_check_out - booking.actual_check_in if booking.actual_check_in else timedelta(hours=20)
        booking.actual_check_out = utcnow() - timedelta(hours=hours)
        booking.actual_check_in = booking.actual_check_out - max(stay, timedelta(hours=1))
        await session.commit()
        print(f"OK: {booking.room_id} now looks empty for {hours:g} hours.")


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 10.0))
