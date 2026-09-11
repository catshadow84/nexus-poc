import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .devices import registry
from .state import store
from .mqtt_bus import bus
from .broadcast import broadcaster
from .booking_service import get_booking as _get_booking, check_out as _check_out


log = logging.getLogger("nora.tools")


# in-memory stub store for service orders (persist later)
SERVICE_ORDERS: dict[str, dict] = {}


async def _issue_command(device_id: str, value: dict) -> dict:
    dev = registry.get(device_id)
    cmd = dev.make_command(value)
    store.set_desired(device_id, cmd.value, cmd.id)
    await bus.publish(f"{dev.topic_base}/command", cmd.model_dump(mode="json"))
    await broadcaster.broadcast({"type": "state", "data": store.snapshot()})
    return {"device": device_id, "value": cmd.value, "command_id": str(cmd.id)}


async def tool_get_room_state(session, **_):
    return store.snapshot()


async def tool_set_light(session, power, brightness=80, color="warm", **_):
    return await _issue_command(
        "light", {"power": power, "brightness": brightness, "color": color}
    )


async def tool_set_thermostat(session, target_c, mode="cool", **_):
    return await _issue_command(
        "thermostat", {"target_c": float(target_c), "mode": mode}
    )


async def tool_set_curtain(session, open_pct, **_):
    return await _issue_command("curtain", {"open_pct": int(open_pct)})


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


async def tool_create_service_order(session, item, quantity=1, **_):
    order_id = str(uuid4())
    order = {
        "id": order_id,
        "item": item,
        "quantity": int(quantity),
        "status": "placed",
        "created_at": datetime.utcnow().isoformat(),
    }
    SERVICE_ORDERS[order_id] = order
    log.info("service order created: %s", order)
    return order


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