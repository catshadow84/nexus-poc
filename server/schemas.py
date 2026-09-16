from pydantic import BaseModel, Field, EmailStr
from typing import Literal, Optional
from uuid import UUID, uuid4
from datetime import datetime


DeviceId = Literal["light", "thermostat", "curtain"]


class CommandPayload(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    action: Literal["set"] = "set"
    value: dict
    issued_at: datetime = Field(default_factory=datetime.utcnow)


class ReportedState(BaseModel):
    id: UUID
    reported: dict
    reported_at: datetime = Field(default_factory=datetime.utcnow)


class LightValue(BaseModel):
    power: Literal["on", "off"]
    brightness: int = Field(ge=0, le=100)
    color: Literal["warm", "neutral", "cool"]


class ThermostatValue(BaseModel):
    target_c: float = Field(ge=10, le=32)
    mode: Literal["cool", "heat", "auto", "off"]


class CurtainValue(BaseModel):
    open_pct: int = Field(ge=0, le=100)


class DeviceState(BaseModel):
    desired: Optional[dict] = None
    reported: Optional[dict] = None
    last_command_id: Optional[UUID] = None
    last_updated: Optional[datetime] = None


class RoomState(BaseModel):
    room_id: str
    devices: dict[str, DeviceState] = {}


class GuestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    preferences: dict = Field(default_factory=dict)


class GuestOut(BaseModel):
    id: str
    name: str
    email: str
    preferences: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingCreate(BaseModel):
    guest_id: str
    room_id: str = "room1"
    planned_check_in: Optional[datetime] = None
    planned_check_out: Optional[datetime] = None


class BookingOut(BaseModel):
    id: str
    guest_id: str
    room_id: str
    status: str
    planned_check_in: Optional[datetime] = None
    planned_check_out: Optional[datetime] = None
    actual_check_in: Optional[datetime] = None
    actual_check_out: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class ChatIn(BaseModel):
    session_id: str
    message: str
    booking_id: str | None = None
    room_id: str = "room1"