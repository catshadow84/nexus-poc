from .models import ServiceOrder
import logging
from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from .state import get_store
from .devices import get_registry
from .mqtt_bus import bus
from .broadcast import broadcaster
from .booking_service import get_booking as _get_booking, check_out as _check_out


log = logging.getLogger("nora.tools")





async def _issue_command(room_id: str, device_id: str, value: dict) -> dict:
    registry = get_registry(room_id)
    store = get_store(room_id)
    dev = registry.get(device_id)
    cmd = dev.make_command(value)
    store.set_desired(device_id, cmd.value, cmd.id)
    await bus.publish(f"{dev.topic_base}/command", cmd.model_dump(mode="json"))
    await broadcaster.broadcast(room_id, {"type": "state", "data": store.snapshot()})
    return {"device": device_id, "value": cmd.value, "command_id": str(cmd.id)}


async def tool_get_room_state(session, room_id="room1", **_):
    return get_store(room_id).snapshot()


async def tool_set_light(session, room_id="room1", power="off", brightness=80, color="warm", **_):
    return await _issue_command(room_id, "light", {"power": power, "brightness": brightness, "color": color})


async def tool_set_thermostat(session, room_id="room1", target_c=22, mode="cool", **_):
    return await _issue_command(room_id, "thermostat", {"target_c": float(target_c), "mode": mode})


async def tool_set_curtain(session, room_id="room1", open_pct=0, **_):
    return await _issue_command(room_id, "curtain", {"open_pct": int(open_pct)})


async def tool_get_booking(session: AsyncSession, booking_id, **_):
    b = await _get_booking(session, booking_id)
    if not b:
        return {"error": "booking not found"}
    return {
        "id": b.id,
        "guest_id": b.guest_id,
        "room_id": b.room_id,
        "status": b.status,
        "actual_check_in": b.actual_check_in.isoformat() if b.actual_check_in else None,
        "actual_check_out": b.actual_check_out.isoformat() if b.actual_check_out else None,
    }


MENU = {
    "coffee": 450,
    "tea": 400,
    "water": 200,
    "sandwich": 1200,
    "snack": 600,
}


async def tool_create_service_order(
    session: AsyncSession,
    item,
    quantity=1,
    booking_id=None,
    **_,
):
    if not booking_id:
        return {"error": "no active booking to attach this order to"}

    price = MENU.get(item.lower(), 500)
    order = ServiceOrder(
        booking_id=booking_id,
        item=item.lower(),
        quantity=int(quantity),
        unit_price_cents=price,
        status="placed",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    log.info("service order %s: %dx %s @ %d cents", order.id, order.quantity, order.item, price)
    return {
        "id": order.id,
        "item": order.item,
        "quantity": order.quantity,
        "unit_price_cents": order.unit_price_cents,
        "status": order.status,
    }


async def tool_checkout(session: AsyncSession, booking_id, **_):
    b = await _get_booking(session, booking_id)
    if not b:
        return {"error": "booking not found"}
    try:
        result = await _check_out(session, b)
    except ValueError as e:
        return {"error": str(e)}
    return {"status": b.status, **result}


TOOLS = {
    "get_room_state": tool_get_room_state,
    "set_light": tool_set_light,
    "set_thermostat": tool_set_thermostat,
    "set_curtain": tool_set_curtain,
    "get_booking": tool_get_booking,
    "create_service_order": tool_create_service_order,
    "checkout": tool_checkout,
}


# JSON schemas for Claude tool use — used later, not yet
TOOL_SCHEMAS = [
    {
        "name": "get_room_state",
        "description": "Read the current state of the room (light, thermostat, curtain).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_light",
        "description": "Change the room light.",
        "input_schema": {
            "type": "object",
            "properties": {
                "power": {"type": "string", "enum": ["on", "off"]},
                "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
                "color": {"type": "string", "enum": ["warm", "neutral", "cool"]},
            },
            "required": ["power"],
        },
    },
    {
        "name": "set_thermostat",
        "description": "Set the thermostat target temperature.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_c": {"type": "number", "minimum": 10, "maximum": 32},
                "mode": {"type": "string", "enum": ["cool", "heat", "auto", "off"]},
            },
            "required": ["target_c"],
        },
    },
    {
        "name": "set_curtain",
        "description": "Move the curtain to a given openness (0 closed, 100 open).",
        "input_schema": {
            "type": "object",
            "properties": {
                "open_pct": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["open_pct"],
        },
    },
    {
        "name": "get_booking",
        "description": "Read a booking by id.",
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    },
    {
        "name": "create_service_order",
        "description": "Place a room service order (coffee, food, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
            },
            "required": ["item"],
        },
    },
    {
        "name": "checkout",
        "description": "Check the guest out and reset the room.",
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    },
]