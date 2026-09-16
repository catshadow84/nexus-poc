from datetime import datetime
from uuid import UUID

from .schemas import RoomState, DeviceState, DeviceId


class StateStore:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.room = RoomState(room_id=room_id)
        for dev in ("light", "thermostat", "curtain"):
            self.room.devices[dev] = DeviceState()

    def set_desired(self, device: DeviceId, value: dict, command_id: UUID):
        ds = self.room.devices[device]
        ds.desired = value
        ds.last_command_id = command_id
        ds.last_updated = datetime.utcnow()

    def set_reported(self, device: DeviceId, value: dict):
        ds = self.room.devices[device]
        ds.reported = value
        ds.last_updated = datetime.utcnow()

    def is_in_sync(self, device: DeviceId) -> bool:
        ds = self.room.devices[device]
        return ds.desired == ds.reported

    def snapshot(self) -> dict:
        return self.room.model_dump(mode="json")


_stores: dict[str, StateStore] = {}


def get_store(room_id: str = "room1") -> StateStore:
    if room_id not in _stores:
        _stores[room_id] = StateStore(room_id)
    return _stores[room_id]


def all_stores() -> dict[str, StateStore]:
    return dict(_stores)