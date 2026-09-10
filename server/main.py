from fastapi import WebSocket, WebSocketDisconnect
from .broadcast import broadcaster
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .mqtt_bus import bus
from .state import store
from .devices import registry


logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bus.start()

    async def handle_state(topic: str, payload: dict):
        # topic: nexus/room1/<device>/state
        parts = topic.split("/")
        if len(parts) != 4 or parts[3] != "state":
            return
        device_id = parts[2]
        reported = payload.get("reported", {})
        store.set_reported(device_id, reported)
        logging.info("state updated %s -> %s", device_id, reported)
        await broadcaster.broadcast({"type": "state", "data": store.snapshot()})

    for device in registry.devices.values():
        await bus.subscribe(f"{device.topic_base}/state", handle_state)

    yield

    await bus.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/room/state")
def room_state():
    return store.snapshot()


@app.post("/room/{device}/command")
async def command(device: str, value: dict):
    try:
        dev = registry.get(device)
    except KeyError:
        raise HTTPException(404, f"unknown device {device}")

    try:
        cmd = dev.make_command(value)
    except Exception as e:
        raise HTTPException(422, str(e))

    store.set_desired(device, cmd.value, cmd.id)

    topic = f"{dev.topic_base}/command"
    await bus.publish(topic, cmd.model_dump(mode="json"))
    await broadcaster.broadcast({"type": "state", "data": store.snapshot()})

    return {
        "ok": True,
        "command_id": str(cmd.id),
        "topic": topic,
        "value": cmd.value,
    }

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        # send current state immediately on connect
        await ws.send_json({"type": "state", "data": store.snapshot()})
        while True:
            # we don't expect messages from the client, but this keeps
            # the connection alive and detects disconnects
            await ws.receive_text()
    except WebSocketDisconnect:
        await broadcaster.disconnect(ws)
    except Exception:
        await broadcaster.disconnect(ws)