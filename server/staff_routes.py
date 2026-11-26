"""Staff login and staff account management."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, bearer, hash_token, require_role, require_staff
from .db import get_session
from .models import StaffToken, StaffUser
from .passwords import check_password_rules, clear_failures, hash_password, is_locked
from .staff import authenticate, clean_username, create_staff, issue_staff_token
from .timeutil import utcnow

router = APIRouter()

Role = Literal["front_desk", "housekeeping", "maintenance", "manager"]


class LoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class AccountCreate(BaseModel):
    username: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=80)
    role: Role
    password: str = Field(max_length=200)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


def public(user: StaffUser) -> dict:
    """Everything about an account except its password hash."""
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/staff/login")
async def staff_login(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    username = clean_username(payload.username)
    if is_locked(username):
        raise HTTPException(429, "Too many wrong attempts. Try again in a few minutes.")
    user = await authenticate(session, username, payload.password)
    if user is None:
        raise HTTPException(401, "Wrong username or password")
    clear_failures(username)
    token, expires_at = await issue_staff_token(session, user)
    await session.commit()
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "role": user.role,
        "name": user.name,
        "username": user.username,
    }


@router.post("/staff/logout")
async def staff_logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    _: Principal = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    if credentials is not None:
        await session.execute(
            update(StaffToken)
            .where(StaffToken.token_hash == hash_token(credentials.credentials))
            .where(StaffToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await session.commit()
    return {"ok": True}


@router.get("/staff/me")
async def staff_me(
    principal: Principal = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    if principal.staff_id:
        user = await session.get(StaffUser, principal.staff_id)
        if user:
            return public(user)
    # The old shared key (or AUTH_DISABLED) has no account of its own.
    return {"id": None, "username": None, "name": "Shared staff key", "role": principal.role, "active": True}


@router.get("/staff/accounts")
async def list_accounts(
    _: Principal = Depends(require_role()),  # managers only
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(StaffUser).order_by(StaffUser.created_at))
    return [public(u) for u in result.scalars()]


@router.post("/staff/accounts", status_code=201)
async def create_account(
    payload: AccountCreate,
    _: Principal = Depends(require_role()),
    session: AsyncSession = Depends(get_session),
):
    try:
        user = await create_staff(
            session, payload.username, payload.name, payload.role, payload.password
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return public(user)


@router.patch("/staff/accounts/{account_id}")
async def update_account(
    account_id: str,
    payload: AccountUpdate,
    principal: Principal = Depends(require_role()),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(StaffUser, account_id)
    if user is None:
        raise HTTPException(404, "account not found")

    is_self = principal.staff_id == user.id
    if is_self and (payload.active is False or (payload.role and payload.role != "manager")):
        raise HTTPException(400, "You cannot deactivate yourself or take away your own manager role")

    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
    if payload.password is not None:
        try:
            check_password_rules(payload.password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        user.password_hash = hash_password(payload.password)
        # A new password signs the person out everywhere.
        await session.execute(
            update(StaffToken)
            .where(StaffToken.staff_id == user.id)
            .where(StaffToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    await session.commit()
    return public(user)