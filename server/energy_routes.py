"""Energy-savings report for managers."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, require_role
from .db import get_session
from .energy import energy_report

router = APIRouter()


@router.get("/energy")
async def energy(
    _: Principal = Depends(require_role("manager")),
    session: AsyncSession = Depends(get_session),
):
    return await energy_report(session)
