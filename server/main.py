from .nora import handle_message
from .scenes import apply_scene, list_scenes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from .db import init_db, get_session
from .models import Guest, Booking
from .schemas import (
    GuestCreate, GuestOut, BookingCreate, BookingOut, ChatIn,
)
from .booking_service import (
    get_guest, get_booking, check_in, check_out,
    RESERVED, CHECKED_IN, CHECKED_OUT,
)
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
    await init_db()
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


# ---------- guests ----------


@app.post("/guests", response_model=GuestOut)
async def create_guest(
    payload: GuestCreate,
    session: AsyncSession = Depends(get_session),
):
    # if a guest with this email exists, update their preferences and return
    existing = await session.execute(
        select(Guest).where(Guest.email == payload.email)
    )
    guest = existing.scalar_one_or_none()
    if guest:
        guest.name = payload.name
        guest.preferences = payload.preferences
        await session.commit()
        await session.refresh(guest)
        return guest

    guest = Guest(
        name=payload.name,
        email=payload.email,
        preferences=payload.preferences,
    )
    session.add(guest)
    await session.commit()
    await session.refresh(guest)
    return guest


@app.get("/guests/{guest_id}", response_model=GuestOut)
async def read_guest(
    guest_id: str,
    session: AsyncSession = Depends(get_session),
):
    g = await get_guest(session, guest_id)
    if not g:
        raise HTTPException(404, "guest not found")
    return g


# ---------- bookings ----------


@app.post("/bookings", response_model=BookingOut)
async def create_booking(
    payload: BookingCreate,
    session: AsyncSession = Depends(get_session),
):
    g = await get_guest(session, payload.guest_id)
    if not g:
        raise HTTPException(404, "guest not found")

    booking = Booking(
        guest_id=payload.guest_id,
        room_id=payload.room_id,
        status=RESERVED,
        planned_check_in=payload.planned_check_in,
        planned_check_out=payload.planned_check_out,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking


@app.get("/bookings/{booking_id}", response_model=BookingOut)
async def read_booking(
    booking_id: str,
    session: AsyncSession = Depends(get_session),
):
    b = await get_booking(session, booking_id)
    if not b:
        raise HTTPException(404, "booking not found")
    return b


@app.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Booking).order_by(Booking.created_at.desc()))
    return list(result.scalars().all())


# ---------- check in / out ----------


@app.post("/bookings/{booking_id}/checkin")
async def do_check_in(
    booking_id: str,
    session: AsyncSession = Depends(get_session),
):
    b = await get_booking(session, booking_id)
    if not b:
        raise HTTPException(404, "booking not found")
    try:
        result = await check_in(session, b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "booking_id": b.id, "status": b.status, **result}


@app.post("/bookings/{booking_id}/checkout")
async def do_check_out(
    booking_id: str,
    session: AsyncSession = Depends(get_session),
):
    b = await get_booking(session, booking_id)
    if not b:
        raise HTTPException(404, "booking not found")
    try:
        result = await check_out(session, b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "booking_id": b.id, "status": b.status, **result}

@app.get("/scenes")
def get_scenes():
    return {"scenes": list_scenes()}


@app.post("/scenes/{name}")
async def run_scene(name: str):
    try:
        applied = await apply_scene(name)
    except KeyError:
        raise HTTPException(404, f"unknown scene {name}")
    return {"ok": True, "scene": name, "applied_devices": applied}

@app.post("/nora/chat")
async def nora_chat(
    payload: ChatIn,
    session: AsyncSession = Depends(get_session),
):
    return await handle_message(
        session,
        payload.session_id,
        payload.message,
        booking_id=payload.booking_id,
    )