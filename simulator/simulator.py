import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4

import asyncio_mqtt as aiomqtt


logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("sim")


ROOMS = ("room1", "room2")
DEVICES = ("light", "central_ac", "bose", "curtain", "door")

state = {
    room: {
        "light": {"power": "off", "brightness": 0, "color": "neutral"},
        "central_ac": {"current_c": 24.0, "target_c": 24.0, "mode": "cool", "power_kw": 0.3},
        "bose": {"power": "off", "volume": 20, "playing": False},
        "curtain": {"open_pct": 0},
        "door": {"locked": True},
    }
    for room in ROOMS
}


def ac_power_kw(st: dict) -> float:
    """A rough energy estimate: off uses nothing, eco is low, otherwise it grows with the gap."""
    if st["mode"] == "off":
        return 0.0
    if st["mode"] == "eco":
        return 0.3
    return round(0.8 + 0.2 * abs(st["current_c"] - st["target_c"]), 2)


async def publish_state(client, room, device):
    topic = f"nexus/{room}/{device}/state"
    payload = {
        "id": str(uuid4()),
        "reported": state[room][device],
        "reported_at": datetime.utcnow().isoformat(),
    }
    await client.publish(topic, json.dumps(payload), retain=True)
    log.info("-> %s/%s %s", room, device, state[room][device])


async def handle_light(client, room, value):
    target = value.copy()
    current = state[room]["light"]
    steps = 5
    for i in range(1, steps + 1):
        for k in target:
            if isinstance(target[k], (int, float)):
                current[k] = current[k] + (target[k] - current[k]) / (steps - i + 1)
            else:
                current[k] = target[k]
        await asyncio.sleep(0.2)
    current.update(target)
    await publish_state(client, room, "light")


async def handle_central_ac(client, room, value):
    target = float(value["target_c"])
    st = state[room]["central_ac"]
    st["target_c"] = target
    st["mode"] = value.get("mode", st["mode"])
    while abs(st["current_c"] - target) > 0.05:
        step = 0.5 if target > st["current_c"] else -0.5
        st["current_c"] = round(st["current_c"] + step, 2)
        st["power_kw"] = ac_power_kw(st)
        await publish_state(client, room, "central_ac")
        await asyncio.sleep(1.0)
    st["current_c"] = target
    st["power_kw"] = ac_power_kw(st)
    await publish_state(client, room, "central_ac")


async def handle_bose(client, room, value):
    st = state[room]["bose"]
    st["power"] = value.get("power", st["power"])
    st["volume"] = int(value.get("volume", st["volume"]))
    # a speaker that is off cannot be playing
    st["playing"] = bool(value.get("playing", st["playing"])) and st["power"] == "on"
    await asyncio.sleep(0.3)
    await publish_state(client, room, "bose")


async def handle_curtain(client, room, value):
    target = int(value["open_pct"])
    st = state[room]["curtain"]
    step = 5 if target > st["open_pct"] else -5
    while st["open_pct"] != target:
        st["open_pct"] += step
        if (step > 0 and st["open_pct"] > target) or (step < 0 and st["open_pct"] < target):
            st["open_pct"] = target
        await publish_state(client, room, "curtain")
        await asyncio.sleep(0.15)

async def handle_door(client, room, value):
    st = state[room]["door"]
    st["locked"] = bool(value.get("locked", True))
    await publish_state(client, room, "door")
    if not st["locked"]:
        await asyncio.sleep(5)  # the door locks itself again
        st["locked"] = True
        await publish_state(client, room, "door")

HANDLERS = {
    "light": handle_light,
    "central_ac": handle_central_ac,
    "bose": handle_bose,
    "curtain": handle_curtain,
    "door": handle_door,
}


async def device_loop(room: str, device: str):
    topic = f"nexus/{room}/{device}/command"
    async with aiomqtt.Client("localhost", 1883) as client:
        await client.subscribe(topic)
        log.info("%s/%s subscribed to %s", room, device, topic)
        await publish_state(client, room, device)
        async with client.messages() as messages:
            async for message in messages:
                try:
                    payload = json.loads(message.payload)
                except Exception:
                    log.warning("bad payload for %s/%s", room, device)
                    continue
                value = payload.get("value", {})
                log.info("<- %s/%s %s", room, device, value)
                try:
                    await HANDLERS[device](client, room, value)
                except Exception as e:
                    log.exception("handler failed for %s/%s: %s", room, device, e)


async def main():
    tasks = []
    for room in ROOMS:
        for device in DEVICES:
            tasks.append(device_loop(room, device))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)