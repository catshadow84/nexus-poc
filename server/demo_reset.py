"""Wipe the demo data so a presentation starts clean.

    python -m server.demo_reset

Removes every guest, booking, service order, guest token, maintenance issue and
room cleaning state. Staff accounts are kept. Reservations that were made in
Apaleo stay there: cancel them in the Apaleo dashboard.
"""

import asyncio
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal
from .models import (
    AccessToken,
    Booking,
    Guest,
    Issue,
    RoomStatus,
    ServiceOrder,
    WebhookEvent,
)

# Children first, so foreign keys never complain.
TABLES = (
    ("orders", ServiceOrder),
    ("guest tokens", AccessToken),
    ("bookings", Booking),
    ("guests", Guest),
    ("maintenance issues", Issue),
    ("room cleaning states", RoomStatus),
    ("webhook events", WebhookEvent),
)


async def count_rows(session: AsyncSession) -> dict[str, int]:
    return {
        label: (await session.execute(select(func.count()).select_from(model))).scalar_one()
        for label, model in TABLES
    }


async def wipe(session: AsyncSession) -> dict[str, int]:
    """Delete the demo data and return how many rows each table had."""
    counts = await count_rows(session)
    for _, model in TABLES:
        await session.execute(delete(model))
    await session.commit()
    return counts


async def main() -> None:
    async with SessionLocal() as session:
        counts = await count_rows(session)
        print("This will delete:")
        for label, n in counts.items():
            print(f"  {n:>5}  {label}")
        print("Staff accounts are kept.")
        if input("Type RESET to continue: ").strip() != "RESET":
            print("Cancelled. Nothing was deleted.")
            sys.exit(1)
        await wipe(session)
    print("Done. Now cancel the test reservations in the Apaleo dashboard,")
    print("and restart the simulator so the rooms start in their default state.")


if __name__ == "__main__":
    asyncio.run(main())
