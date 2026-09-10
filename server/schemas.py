from pydantic import BaseModel, Field
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