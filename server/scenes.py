import logging

from .state import get_store
from .devices import get_registry
from .mqtt_bus import bus
from .broadcast import broadcaster


log = logging.getLogger("scenes")


SCENES: dict[str, dict[str, dict]] = {
    "goodnight": {
        "light": {"power": "off", "brightness": 0, "color": "neutral"},
        "thermostat": {"target_c": 19.0, "mode": "cool"},
        "curtain": {"open_pct": 0},
    },
    "good_morning": {
        "light": {"power": "on", "brightness": 60, "color": "warm"},
        "thermostat": {"target_c": 22.0, "mode": "cool"},
        "curtain": {"open_pct": 70},
    },
    "focus": {
        "light": {"power": "on", "brightness": 100, "color": "cool"},
        "thermostat": {"target_c": 21.0, "mode": "cool"},
        "curtain": {"open_pct": 100},
    },
}


async def apply_scene(room_id: str, name: str) -> list[str]:
    if name not in SCENES:
        raise KeyError(name)

    store = get_store(room_id)
    registry = get_registry(room_id)

    applied: list[str] = []
    for device_id, value in SCENES[name].items():
        try:
            dev = registry.get(device_id)
            cmd = dev.make_command(value)
        except Exception as e:
            log.warning("scene %s room %s skip %s: %s", name, room_id, device_id, e)
            continue

        store.set_desired(device_id, cmd.value, cmd.id)
        await bus.publish(f"{dev.topic_base}/command", cmd.model_dump(mode="json"))
        applied.append(device_id)

    await broadcaster.broadcast(room_id, {"type": "state", "data": store.snapshot()})
    return applied


def list_scenes() -> list[str]:
    return list(SCENES.keys())