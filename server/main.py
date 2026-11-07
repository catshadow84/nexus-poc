import math
from .nora import handle_message
from .scenes import apply_scene, list_scenes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from .db import get_session, SessionLocal
from .models import Guest, Booking, ServiceOrder, WebhookEvent
from .schemas import (
    GuestCreate, GuestOut, BookingCreate, BookingOut, ChatIn, ApaleoBookingCreate, OfferOut, BookingCreatedOut,
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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .mqtt_bus import bus
from .state import get_store, all_stores
from .devices import get_registry
from .timeutil import utcnow
import os
import secrets
from sqlalchemy.exc import IntegrityError
from .apaleo_sync import process_event
from datetime import date, datetime, time as dtime

from .apaleo import (
    ApaleoError, extract_ids, get_client, simplify_offer, split_name, validate_stay,
)

from .auth import (
    Principal, auth_disabled, can_access_room, get_principal, issue_guest_token,
    optional_principal, owned_booking, principal_from_token, require_staff, room_access,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if auth_disabled():
        logging.warning("AUTH_DISABLED=1: every endpoint is open. Development only!")
    await bus.start()

    async def handle_state(topic: str, payload: dict):
        # topic: nexus/{room}/{device}/state
        parts = topic.split("/")
        if len(parts) != 4 or parts[3] != "state":
            return
        room_id, device_id = parts[1], parts[2]
        reported = payload.get("reported", {})
        get_store(room_id).set_reported(device_id, reported)
        logging.info("state updated room=%s %s -> %s", room_id, device_id, reported)
        await broadcaster.broadcast(
            room_id,
            {"type": "state", "data": get_store(room_id).snapshot()},
        )

    await bus.subscribe("nexus/+/+/state", handle_state)

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


@app.get("/rooms/{room_id}/state")
def room_state(room_id: str = Depends(room_access)):
    return get_store(room_id).snapshot()

@app.post("/rooms/{room_id}/device/{device}/command")
async def command(device: str, value: dict, room_id: str = Depends(room_access)):
    registry = get_registry(room_id)
    store = get_store(room_id)
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
    await broadcaster.broadcast(room_id, {"type": "state", "data": store.snapshot()})

    return {
        "ok": True,
        "command_id": str(cmd.id),
        "topic": topic,
        "value": cmd.value,
    }

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, room_id: str = "room1"):
    await ws.accept()
    if not auth_disabled():
        # The first message must be {"type": "auth", "token": "..."}.
        try:
            message = await asyncio.wait_for(ws.receive_json(), timeout=5)
            async with SessionLocal() as session:
                principal = await principal_from_token(session, str(message.get("token", "")))
                allowed = await can_access_room(session, principal, room_id)
        except (WebSocketDisconnect, asyncio.TimeoutError, HTTPException, ValueError, AttributeError):
            await ws.close(code=1008)
            return
        if not allowed:
            await ws.close(code=1008)
            return
    await broadcaster.register(room_id, ws)
    try:
        await ws.send_json({
            "type": "state",
            "data": get_store(room_id).snapshot(),
        })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await broadcaster.disconnect(room_id, ws)
    except Exception:
        await broadcaster.disconnect(room_id, ws)


# ---------- guests ----------


@app.post("/guests", response_model=GuestOut)
async def create_guest(
    payload: GuestCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal | None = Depends(optional_principal),
):
    # if a guest with this email exists, update their preferences and return
    existing = await session.execute(
        select(Guest).where(Guest.email == payload.email.lower())
    )
    guest = existing.scalar_one_or_none()
    if guest:
        # Only staff may change an existing guest's data.
        if principal is not None and principal.is_staff:
            guest.name = payload.name
            if payload.preferences:
                guest.preferences = payload.preferences
            await session.commit()
            await session.refresh(guest)
        return guest

    guest = Guest(
        name=payload.name,
        email=payload.email.lower(),
        preferences=payload.preferences,
    )
    session.add(guest)
    await session.commit()
    await session.refresh(guest)
    return guest

@app.get("/guests/lookup")
async def lookup_guest(
    email: str,
    _: Principal = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Guest).where(Guest.email == email.lower())
    )
    guest = result.scalar_one_or_none()
    if not guest:
        return {"found": False}

    stays_res = await session.execute(
        select(Booking)
        .where(Booking.guest_id == guest.id)
        .where(Booking.status == "CHECKED_OUT")
        .order_by(Booking.actual_check_out.desc())
    )
    stays = list(stays_res.scalars().all())

    return {
        "found": True,
        "guest": {
            "id": guest.id,
            "name": guest.name,
            "email": guest.email,
            "preferences": guest.preferences,
        },
        "stay_count": len(stays),
        "last_stay": (
            stays[0].actual_check_out.isoformat() if stays and stays[0].actual_check_out else None
        ),
    }


@app.get("/guests/{guest_id}", response_model=GuestOut)
async def read_guest(
    guest_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
):
    if not (principal.is_staff or principal.guest_id == guest_id):
        raise HTTPException(404, "guest not found")
    g = await get_guest(session, guest_id)
    if not g:
        raise HTTPException(404, "guest not found")
    return g


# ---------- bookings ----------


@app.post("/bookings", response_model=BookingOut)
async def create_booking(
    payload: BookingCreate,
    _: Principal = Depends(require_staff),
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

@app.post("/webhooks/apaleo/{token}")
async def apaleo_webhook(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    expected = os.getenv("APALEO_WEBHOOK_TOKEN", "")
    if not expected or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(404, "Not found")  # reveal nothing about the endpoint

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload")

    topic = str(payload.get("topic", ""))
    if topic.lower() == "system":  # Apaleo's health check when subscribing
        return {"ok": True}

    event_id = payload.get("id")
    if event_id and await session.get(WebhookEvent, event_id):
        return {"ok": True, "duplicate": True}

    try:
        outcome = await process_event(session, get_client(), payload)
    except ApaleoError:
        logging.exception("Apaleo webhook processing failed")
        raise HTTPException(503, "Try again later")  # Apaleo will retry

    if event_id:
        session.add(WebhookEvent(
            id=event_id,
            topic=topic,
            type=str(payload.get("type", "")),
            entity_id=(payload.get("data") or {}).get("entityId"),
        ))
    try:
        await session.commit()
    except IntegrityError:  # the same event arrived twice at once
        await session.rollback()
        return {"ok": True, "duplicate": True}

    logging.info("Apaleo webhook %s/%s -> %s", topic, payload.get("type"), outcome)
    return {"ok": True}

@app.get("/offers", response_model=list[OfferOut])
async def list_offers(arrival: date, departure: date, adults: int = 2):
    try:
        validate_stay(arrival, departure, adults)
    except ValueError as e:
        raise HTTPException(422, str(e))
    client = get_client()
    try:
        offers = await client.get_offers(
            client.property_id, arrival.isoformat(), departure.isoformat(), adults
        )
    except ApaleoError:
        logging.exception("Apaleo offers request failed")
        raise HTTPException(502, "Booking provider unavailable")
    return [simplify_offer(o) for o in offers]


@app.post("/bookings/apaleo", response_model=BookingCreatedOut)
async def create_apaleo_booking(
    payload: ApaleoBookingCreate,
    session: AsyncSession = Depends(get_session),
):
    guest = await get_guest(session, payload.guest_id)
    if not guest:
        raise HTTPException(404, "guest not found")
    try:
        validate_stay(payload.arrival, payload.departure, payload.adults)
    except ValueError as e:
        raise HTTPException(422, str(e))

    client = get_client()
    arrival = payload.arrival.isoformat()
    departure = payload.departure.isoformat()

    # Look the offer up again ourselves: price and guarantee come from Apaleo.
    try:
        offers = await client.get_offers(
            client.property_id, arrival, departure, payload.adults
        )
    except ApaleoError:
        logging.exception("Apaleo offers request failed")
        raise HTTPException(502, "Booking provider unavailable")
    offer = next(
        (o for o in offers if o["ratePlan"]["id"] == payload.rate_plan_id), None
    )
    if offer is None:
        raise HTTPException(409, "That offer is no longer available")
    if offer.get("minGuaranteeType") == "Prepayment":
        raise HTTPException(409, "This rate needs payment, which is not supported yet")

    first_name, last_name = split_name(guest.name)
    try:
        result = await client.create_booking(
            offer, arrival, departure, payload.adults,
            first_name, last_name, guest.email,
        )
    except ApaleoError:
        logging.exception("Apaleo create booking failed")
        raise HTTPException(502, "Booking provider rejected the request")
    try:
        apaleo_booking_id, apaleo_reservation_id = extract_ids(result)
    except ApaleoError:
        logging.error("Apaleo booking CREATED but IDs not understood: %s", result)
        raise HTTPException(502, "Booking created but could not be recorded; contact staff")

    booking = Booking(
        guest_id=payload.guest_id,
        room_id=payload.room_id,
        status=RESERVED,
        planned_check_in=datetime.combine(payload.arrival, dtime.min),
        planned_check_out=datetime.combine(payload.departure, dtime.min),
        apaleo_booking_id=apaleo_booking_id,
        apaleo_reservation_id=apaleo_reservation_id,
    )
    session.add(booking)
    try:
        guest_token = await issue_guest_token(session, booking)
        await session.commit()
    except Exception:
        logging.error(
            "Apaleo booking %s / reservation %s created but local save failed",
            apaleo_booking_id, apaleo_reservation_id,
        )
        raise
    await session.refresh(booking)
    return BookingCreatedOut(
        **BookingOut.model_validate(booking).model_dump(), guest_token=guest_token
    )
@app.get("/bookings/active", response_model=BookingOut | None)
async def active_booking(
    room_id: str = "room1",
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_staff),
):
    result = await session.execute(
        select(Booking)
        .where(Booking.room_id == room_id)
        .where(Booking.status == CHECKED_IN)
    )
    return result.scalars().first()

@app.get("/bookings/{booking_id}/summary")
async def booking_summary(
    b: Booking = Depends(owned_booking),
    session: AsyncSession = Depends(get_session),
):
    booking_id = b.id

    guest = await get_guest(session, b.guest_id)

    orders_res = await session.execute(
        select(ServiceOrder).where(ServiceOrder.booking_id == booking_id)
    )
    orders = list(orders_res.scalars().all())

    # nights: floor at 1 so demos look sane
    if b.actual_check_in:
        end = b.actual_check_out or utcnow()
        delta_days = (end - b.actual_check_in).total_seconds() / 86400
        nights = max(1, math.ceil(delta_days))
    else:
        nights = 1

    ROOM_RATE_CENTS = 22000  # $220/night
    room_charge_cents = nights * ROOM_RATE_CENTS
    orders_charge_cents = sum(o.unit_price_cents * o.quantity for o in orders)
    total_cents = room_charge_cents + orders_charge_cents

    # rough carbon estimate for the demo
    carbon_kg = round(nights * 8.0 + sum(o.quantity * 0.4 for o in orders), 2)

    return {
        "booking_id": b.id,
        "status": b.status,
        "guest": {
            "id": guest.id if guest else None,
            "name": guest.name if guest else None,
            "email": guest.email if guest else None,
        },
        "check_in": b.actual_check_in.isoformat() if b.actual_check_in else None,
        "check_out": b.actual_check_out.isoformat() if b.actual_check_out else None,
        "nights": nights,
        "room_charge_cents": room_charge_cents,
        "orders": [
            {
                "id": o.id,
                "item": o.item,
                "quantity": o.quantity,
                "unit_price_cents": o.unit_price_cents,
                "line_total_cents": o.unit_price_cents * o.quantity,
                "status": o.status,
            }
            for o in orders
        ],
        "orders_total_cents": orders_charge_cents,
        "total_cents": total_cents,
        "carbon_kg": carbon_kg,
        "currency": "USD",
    }

@app.get("/bookings/{booking_id}", response_model=BookingOut)
async def read_booking(b: Booking = Depends(owned_booking)):
    return b


@app.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    _: Principal = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Booking).order_by(Booking.created_at.desc()))
    return list(result.scalars().all())


# ---------- check in / out ----------

@app.post("/bookings/{booking_id}/checkin")
async def do_check_in(
    b: Booking = Depends(owned_booking),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await check_in(session, b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "booking_id": b.id, "status": b.status, **result}


@app.post("/bookings/{booking_id}/checkout")
async def do_check_out(
    b: Booking = Depends(owned_booking),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await check_out(session, b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "booking_id": b.id, "status": b.status, **result}


@app.post("/bookings/{booking_id}/token")
async def reissue_token(
    b: Booking = Depends(owned_booking),
    _: Principal = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """Staff only: issue a fresh guest token. Older tokens stop working."""
    token = await issue_guest_token(session, b)
    await session.commit()
    return {"booking_id": b.id, "guest_token": token}

@app.get("/scenes")
def get_scenes():
    return {"scenes": list_scenes()}


@app.post("/rooms/{room_id}/scenes/{name}")
async def run_scene(name: str, room_id: str = Depends(room_access)):
    try:
        applied = await apply_scene(room_id, name)
    except KeyError:
        raise HTTPException(404, f"unknown scene {name}")
    return {"ok": True, "scene": name, "applied_devices": applied}

@app.get("/rooms")
def list_rooms(_: Principal = Depends(require_staff)):
    return {"rooms": list(all_stores().keys())}


@app.post("/nora/chat")
async def nora_chat(
    payload: ChatIn,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
):
    booking_id = payload.booking_id
    if not principal.is_staff:
        if booking_id not in (None, principal.booking_id):
            raise HTTPException(403, "Not your booking")
        booking_id = principal.booking_id
        booking = await get_booking(session, booking_id)
        if not booking or booking.status != CHECKED_IN:
            raise HTTPException(403, "Check in first")
    return await handle_message(
        session,
        payload.session_id,
        payload.message,
        booking_id=booking_id,
        room_id=payload.room_id,
    )