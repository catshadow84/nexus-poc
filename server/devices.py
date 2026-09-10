from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel

from .schemas import CommandPayload


class Device(ABC):
    id: str
    topic_base: str

    @abstractmethod
    def validate(self, value: dict) -> BaseModel: ...

    def make_command(self, value: dict) -> CommandPayload:
        validated = self.validate(value)
        return CommandPayload(value=validated.model_dump())


class LightDevice(Device):
    id = "light"

    def __init__(self, room_id: str):
        self.topic_base = f"nexus/{room_id}/light"

    def validate(self, value):
        from .schemas import LightValue
        return LightValue(**value)


class ThermostatDevice(Device):
    id = "thermostat"

    def __init__(self, room_id: str):
        self.topic_base = f"nexus/{room_id}/thermostat"

    def validate(self, value):
        from .schemas import ThermostatValue
        return ThermostatValue(**value)


class CurtainDevice(Device):
    id = "curtain"

    def __init__(self, room_id: str):
        self.topic_base = f"nexus/{room_id}/curtain"

    def validate(self, value):
        from .schemas import CurtainValue
        return CurtainValue(**value)


class DeviceRegistry:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.devices: dict[str, Device] = {
            "light": LightDevice(room_id),
            "thermostat": ThermostatDevice(room_id),
            "curtain": CurtainDevice(room_id),
        }

    def get(self, device_id: str) -> Device:
        if device_id not in self.devices:
            raise KeyError(device_id)
        return self.devices[device_id]


registry = DeviceRegistry(room_id="room1")