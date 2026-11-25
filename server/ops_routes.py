"""Housekeeping (room cleaning status) and maintenance (issues) endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, has_role, require_role
from .booking_service import CHECKED_IN
from .db import get_session
from .models import Booking, Issue, RoomStatus, StaffUser
from .ops import CLEAN_STATES, ISSUE_STATES, known_rooms, set_room_state
from .timeutil import utcnow

router = APIRouter()

CleanState = Literal["dirty", "cleaning", "clean", "inspected"]
IssueState = Literal["open", "in_progress", "resolved"]


class StatusIn(BaseModel):
    state: CleanState


class IssueCreate(BaseModel):
    room_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=3, max_length=120)
    details: str = Field(default="", max_length=1000)


class IssueUpdate(BaseModel):
    status: IssueState


async def actor_name(session: AsyncSession, principal: Principal) -> str:
    if principal.staff_id:
        user = await session.get(StaffUser, principal.staff_id)
        if user:
            return user.name
    return "Shared staff key"


def issue_out(issue: Issue) -> dict:
    return {
        "id": issue.id,
        "room_id": issue.room_id,
        "title": issue.title,
        "details": issue.details,
        "status": issue.status,
        "reported_by": issue.reported_by,
        "updated_by": issue.updated_by,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
    }


async def room_rows(session: AsyncSession) -> list[dict]:
    rooms = await known_rooms(session)
    statuses = {r.room_id: r for r in (await session.execute(select(RoomStatus))).scalars()}
    occupied = set(
        (
            await session.execute(
                select(Booking.room_id).where(Booking.status == CHECKED_IN)
            )
        ).scalars()
    )
    open_counts = dict(
        (
            await session.execute(
                select(Issue.room_id, func.count())
                .where(Issue.status != "resolved")
                .group_by(Issue.room_id)
            )
        ).all()
    )
    rows = []
    for room_id in sorted(rooms):
        status = statuses.get(room_id)
        rows.append(
            {
                "room_id": room_id,
                "occupied": room_id in occupied,
                "clean_state": status.clean_state if status else "clean",
                "updated_at": status.updated_at.isoformat() if status else None,
                "updated_by": status.updated_by if status else None,
                "open_issues": open_counts.get(room_id, 0),
            }
        )
    return rows


@router.get("/housekeeping/rooms")
async def housekeeping_rooms(
    _: Principal = Depends(require_role("front_desk", "housekeeping")),
    session: AsyncSession = Depends(get_session),
):
    rows = await room_rows(session)
    summary = {state: 0 for state in CLEAN_STATES}
    for row in rows:
        summary[row["clean_state"]] += 1
    return {"rooms": rows, "summary": summary}


@router.post("/housekeeping/rooms/{room_id}/status")
async def set_status(
    room_id: str,
    payload: StatusIn,
    principal: Principal = Depends(require_role("front_desk", "housekeeping")),
    session: AsyncSession = Depends(get_session),
):
    # Housekeepers mark rooms cleaning or clean. Inspecting or re-marking dirty is a supervisor's job.
    if not has_role(principal, "front_desk") and payload.state not in ("cleaning", "clean"):
        raise HTTPException(403, "Housekeeping can mark a room cleaning or clean")
    if room_id not in await known_rooms(session):
        raise HTTPException(404, "room not found")
    await set_room_state(session, room_id, payload.state, await actor_name(session, principal))
    await session.commit()
    return next(r for r in await room_rows(session) if r["room_id"] == room_id)


@router.get("/maintenance/issues")
async def list_issues(
    status: str = "unresolved",
    _: Principal = Depends(require_role("front_desk", "housekeeping", "maintenance")),
    session: AsyncSession = Depends(get_session),
):
    if status not in ("unresolved", "all", *ISSUE_STATES):
        raise HTTPException(422, "status must be unresolved, all, open, in_progress or resolved")
    query = select(Issue).order_by(Issue.created_at.desc())
    if status == "unresolved":
        query = query.where(Issue.status != "resolved")
    elif status != "all":
        query = query.where(Issue.status == status)
    return [issue_out(i) for i in (await session.execute(query)).scalars()]


@router.post("/maintenance/issues", status_code=201)
async def report_issue(
    payload: IssueCreate,
    principal: Principal = Depends(require_role("front_desk", "housekeeping", "maintenance")),
    session: AsyncSession = Depends(get_session),
):
    if payload.room_id not in await known_rooms(session):
        raise HTTPException(404, "room not found")
    name = await actor_name(session, principal)
    issue = Issue(
        room_id=payload.room_id,
        title=payload.title.strip(),
        details=payload.details.strip(),
        reported_by=name,
        updated_by=name,
    )
    session.add(issue)
    await session.commit()
    return issue_out(issue)


@router.patch("/maintenance/issues/{issue_id}")
async def update_issue(
    issue_id: str,
    payload: IssueUpdate,
    principal: Principal = Depends(require_role("front_desk", "maintenance")),
    session: AsyncSession = Depends(get_session),
):
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404, "issue not found")
    issue.status = payload.status
    issue.updated_at = utcnow()
    issue.updated_by = await actor_name(session, principal)
    issue.resolved_at = utcnow() if payload.status == "resolved" else None
    await session.commit()
    return issue_out(issue)