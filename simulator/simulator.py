import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4

import asyncio_mqtt as aiomqtt


logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("sim")


ROOM = "room1"
DEVICES = ("light", "thermostat", "curtain")

# current physical state (starts from a "cold room" default)
state = {
    "light": {"power": "off", "brightness": 0, "color": "neutral"},
    "thermostat": {"current_c": 24.0, "target_c": 24.0, "mode": "cool"},
    "curtain": {"open_pct": 0},
}


async def publish_state(client, device):
    topic = f"nexus/{ROOM}/{device}/state"
    payload = {
        "id": str(uuid4()),
        "reported": state[device],
        "reported_at": datetime.utcnow().isoformat(),
    }
    await client.publish(topic, json.dumps(payload), retain = True)
    log.info("→ %s %s", device, state[device])


async def handle_light(client, value: dict):
    # Simulate a ramp-in for brightness over 1s
    target = value.copy()
    current = state["light"]
    steps = 5
    for i in range(1, steps + 1):
        for k in target:
            if isinstance(target[k], (int, float)):
                current[k] = current[k] + (target[k] - current[k]) / (steps - i + 1)
            else:
                current[k] = target[k]
        await asyncio.sleep(0.2)
    current.update(target)  # snap to exact
    await publish_state(client, "light")


async def handle_thermostat(client, value: dict):
    target = float(value["target_c"])
    state["thermostat"]["target_c"] = target
    state["thermostat"]["mode"] = value.get("mode", state["thermostat"]["mode"])
    # Simulate drift toward target at 0.5C per second
    while abs(state["thermostat"]["current_c"] - target) > 0.05:
        step = 0.5 if target > state["thermostat"]["current_c"] else -0.5
        state["thermostat"]["current_c"] = round(
            state["thermostat"]["current_c"] + step, 2
        )
        await publish_state(client, "thermostat")
        await asyncio.sleep(1.0)
    state["thermostat"]["current_c"] = target
    await publish_state(client, "thermostat")


async def handle_curtain(client, value: dict):
    target = int(value["open_pct"])
    current = state["curtain"]["open_pct"]
    step = 5 if target > current else -5
    while current != target:
        current += step
        if (step > 0 and current > target) or (step < 0 and current < target):
            current = target
        state["curtain"]["open_pct"] = current
        await publish_state(client, "curtain")
        await asyncio.sleep(0.15)


HANDLERS = {
    "light": handle_light,
    "thermostat": handle_thermostat,
    "curtain": handle_curtain,
}


async def device_loop(device: str):
    topic = f"nexus/{ROOM}/{device}/command"
    async with aiomqtt.Client("localhost", 1883) as client:
        await client.subscribe(topic)
        log.info("%s subscribed to %s", device, topic)
        await publish_state(client, device)
        async with client.messages() as messages:
            async for message in messages:
                try:
                    payload = json.loads(message.payload)
                except Exception:
                    log.warning("bad payload for %s", device)
                    continue
                value = payload.get("value", {})
                log.info("← %s %s", device, value)
                try:
                    await HANDLERS[device](client, value)
                except Exception as e:
                    log.exception("handler failed for %s: %s", device, e)


async def main():
    await asyncio.gather(*(device_loop(d) for d in DEVICES))


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main()) 