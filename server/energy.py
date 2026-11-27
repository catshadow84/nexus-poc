"""Estimated air-conditioning energy saved by switching a room to eco at check-out.

This is an estimate, not a meter reading. When a guest checks out, NEXUS puts the
central air conditioning into eco mode. Until the next guest checks in, the room
uses ECO_KW instead of the OCCUPIED_KW it would use if it were left running.
The difference, multiplied by the hours the room stood empty, is the saving.

All numbers can be changed in .env (see .env.example).
"""

import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Booking
from .ops import known_rooms
from .state import all_stores
from .timeutil import utcnow


@dataclass(frozen=True)
class EnergyConfig:
    occupied_kw: float
    eco_kw: float
    price_per_kwh: float
    currency: str
    kg_co2_per_kwh: float
    cap_hours: float


def _num(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        return default
    return value if value >= 0 else default


def energy_config() -> EnergyConfig:
    return EnergyConfig(
        occupied_kw=_num("AC_OCCUPIED_KW", 1.2),
        eco_kw=_num("AC_ECO_KW", 0.3),  # the simulator's eco power
        price_per_kwh=_num("ENERGY_PRICE_PER_KWH", 0.20),
        currency=(os.getenv("ENERGY_CURRENCY", "USD").strip().upper() or "USD")[:3],
        kg_co2_per_kwh=_num("GRID_KG_CO2_PER_KWH", 0.5),
        # A room empty for weeks is not a saving we can prove, so one stretch counts at most this long.
        cap_hours=_num("ENERGY_CAP_HOURS", 72),
    )


def vacant_hours(stays: list[tuple[datetime, datetime | None]], now: datetime, cap_hours: float) -> list[float]:
    """Hours each empty stretch lasted. `stays` is one room's (check-in, check-out) pairs.

    A stretch starts at a check-out and ends at the next check-in, or now if nobody
    has arrived since. A guest who is still in the room starts no stretch.
    """
    ordered = sorted(stays, key=lambda s: s[0])
    stretches: list[float] = []
    for i, (_, out) in enumerate(ordered):
        if out is None:
            continue
        end = ordered[i + 1][0] if i + 1 < len(ordered) else now
        end = min(end, now)
        hours = max(0.0, (end - out).total_seconds() / 3600)
        stretches.append(min(hours, cap_hours))
    return stretches


def _live(room_id: str) -> dict:
    store = all_stores().get(room_id)
    reported = (store.room.devices.get("central_ac").reported if store else None) or {}
    return {"live_mode": reported.get("mode"), "live_kw": reported.get("power_kw")}


async def energy_report(session: AsyncSession, now: datetime | None = None) -> dict:
    now = now or utcnow()
    cfg = energy_config()
    result = await session.execute(
        select(Booking).where(
            Booking.status.in_(("CHECKED_IN", "CHECKED_OUT")),
            Booking.actual_check_in.is_not(None),
        )
    )
    per_room: dict[str, list[tuple[datetime, datetime | None]]] = {}
    for b in result.scalars():
        out = b.actual_check_out if b.status == "CHECKED_OUT" else None
        per_room.setdefault(b.room_id, []).append((b.actual_check_in, out))

    saved_kw = max(cfg.occupied_kw - cfg.eco_kw, 0.0)
    rooms = []
    for room_id in sorted(await known_rooms(session)):
        stretches = vacant_hours(per_room.get(room_id, []), now, cfg.cap_hours)
        hours = sum(stretches)
        kwh = hours * saved_kw
        rooms.append(
            {
                "room_id": room_id,
                "checkouts": len(stretches),
                "vacant_hours": round(hours, 1),
                "kwh_saved": round(kwh, 2),
                "money_saved": round(kwh * cfg.price_per_kwh, 2),
                "co2_kg_saved": round(kwh * cfg.kg_co2_per_kwh, 2),
                **_live(room_id),
            }
        )

    kwh_total = sum(r["kwh_saved"] for r in rooms)
    return {
        "generated_at": now.isoformat(),
        "estimated": True,
        "currency": cfg.currency,
        "assumptions": {
            "occupied_kw": cfg.occupied_kw,
            "eco_kw": cfg.eco_kw,
            "price_per_kwh": cfg.price_per_kwh,
            "kg_co2_per_kwh": cfg.kg_co2_per_kwh,
            "cap_hours": cfg.cap_hours,
        },
        "totals": {
            "checkouts": sum(r["checkouts"] for r in rooms),
            "vacant_hours": round(sum(r["vacant_hours"] for r in rooms), 1),
            "kwh_saved": round(kwh_total, 2),
            "money_saved": round(sum(r["money_saved"] for r in rooms), 2),
            "co2_kg_saved": round(sum(r["co2_kg_saved"] for r in rooms), 2),
        },
        "rooms": rooms,
    }
