"""NORA powered by Claude, through the Anthropic Messages API (plain httpx, no extra package).

How it stays safe:
- The model never chooses the booking or the room. Those come from the signed-in guest.
- Room service only accepts items on the menu, at most MAX_QTY at a time.
- Check-out only runs when the guest's own latest message is an explicit confirmation.
- If the Claude call fails before anything happened, the caller falls back to the
  rule-based NORA, so the app keeps working without internet or without credit.
- The API key is read from the environment and is never logged or sent to the app.
"""

import logging
import os
import re
import time
from collections import defaultdict, deque

import httpx

from .nora_tools import MENU, TOOLS
from .state import get_store

log = logging.getLogger("nora.llm")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_QTY = 10
MAX_ROUNDS = 5
HISTORY_TURNS = 6  # whole exchanges (a question, its tool calls and the answer)
TOOL_RESULT_CHARS = 1500
NUDGE = "Now answer the guest in one or two short sentences."

_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))  # key -> turns, each a list of messages
_calls: dict[str, list[float]] = defaultdict(list)


def reset_memory() -> None:
    _history.clear()
    _calls.clear()


def enabled() -> bool:
    if os.getenv("NORA_MODE", "auto").strip().lower() == "rules":
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def model_name() -> str:
    return os.getenv("NORA_MODEL", "").strip() or DEFAULT_MODEL


def _max_per_hour() -> int:
    try:
        return max(1, int(os.getenv("NORA_MAX_PER_HOUR", "60")))
    except ValueError:
        return 60


def within_budget(key: str) -> bool:
    """A small per-guest cap, so a loop or a prank cannot run up the bill."""
    now = time.time()
    recent = [t for t in _calls[key] if now - t < 3600]
    _calls[key] = recent
    if len(recent) >= _max_per_hour():
        return False
    recent.append(now)
    return True


def is_checkout_confirmation(text: str) -> bool:
    """True only for a clear 'yes, check me out' style message."""
    m = re.sub(r"[^\w\s']", " ", text.lower())
    wants = re.search(r"\b(check me out|check out|checkout)\b", m)
    yes = re.search(r"\b(yes|yeah|yep|confirm|confirmed|sure|please do)\b", m)
    return bool(wants and yes)


# ---------- what the model is allowed to do ----------

TOOL_SCHEMAS = [
    {
        "name": "set_light",
        "description": "Change the room light. Give only what should change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "power": {"type": "string", "enum": ["on", "off"]},
                "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
                "color": {"type": "string", "enum": ["warm", "neutral", "cool"]},
            },
        },
    },
    {
        "name": "set_central_ac",
        "description": (
            "Set the central air conditioning. mode 'eco' saves energy while the guest is out; "
            "'off' switches it off. target_c must be between 16 and 30."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_c": {"type": "number", "minimum": 16, "maximum": 30},
                "mode": {"type": "string", "enum": ["cool", "heat", "auto", "eco", "off"]},
            },
        },
    },
    {
        "name": "set_bose",
        "description": "Control the Bose speaker: power, volume (0-100), play or pause.",
        "input_schema": {
            "type": "object",
            "properties": {
                "power": {"type": "string", "enum": ["on", "off"]},
                "volume": {"type": "integer", "minimum": 0, "maximum": 100},
                "playing": {"type": "boolean"},
            },
        },
    },
    {
        "name": "set_curtain",
        "description": "Move the curtain: 0 is closed, 100 is fully open.",
        "input_schema": {
            "type": "object",
            "properties": {"open_pct": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["open_pct"],
        },
    },
    {
        "name": "order_room_service",
        "description": "Order from the room service menu. Only menu items can be ordered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "enum": list(MENU)},
                "quantity": {"type": "integer", "minimum": 1, "maximum": MAX_QTY},
            },
            "required": ["item"],
        },
    },
    {
        "name": "get_bill",
        "description": "Read the guest's charges so far (room price and room service).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_room_state",
        "description": "Read what the room is doing right now.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_out",
        "description": (
            "End the guest's stay. Call it ONLY after the guest's latest message clearly confirmed, "
            "for example 'yes, check me out'. Otherwise ask them to confirm first."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

# What the app shows for each action (the app knows these names).
ACTION_NAME = {
    "set_light": "set_light",
    "set_central_ac": "set_central_ac",
    "set_bose": "set_bose",
    "set_curtain": "set_curtain",
    "order_room_service": "create_service_order",
    "check_out": "checkout",
}


def _reported(room_id: str, device: str) -> dict:
    snap = get_store(room_id).snapshot()
    return (snap.get("devices", {}).get(device, {}).get("reported")) or {}


def system_prompt(guest_name, room_id, booking, currency, checkout_text) -> str:
    light = _reported(room_id, "light")
    ac = _reported(room_id, "central_ac")
    curtain = _reported(room_id, "curtain")
    bose = _reported(room_id, "bose")
    menu = ", ".join(f"{k} {v / 100:.2f}" for k, v in MENU.items())
    first = guest_name.split()[0] if guest_name else "unknown"
    return f"""You are NORA, the AI concierge of a NEXUS hotel room. You are warm, brief and practical.

Guest first name: {first}. Room: {room_id}. {checkout_text}
Room service menu (prices in {currency}): {menu}.
Right now: light {light or 'unknown'}; air conditioning {ac or 'unknown'}; curtain {curtain or 'unknown'}; speaker {bose or 'unknown'}.

Rules:
- Use the tools to act. Never say something was done unless its tool result says ok.
- Reply in 1-3 short sentences of plain text. No markdown, no lists.
- Answer in the language the guest writes in.
- If the guest is cold or hot, change the air conditioning target by about 2 degrees from the current target. Stay between 16 and 30.
- If the guest says they are going out or leaving the room, use eco mode.
- Check-out: first ask the guest to reply "yes, check me out". Only call check_out after they said so in their latest message.
- You cannot open the door. Tell the guest to tap Unlock on the Door card of the room screen, or type their door code on the keypad.
- Late or early check-out, extra towels, complaints and anything you have no tool for: say so briefly and suggest the front desk.
- Never invent bookings, prices, orders or menu items.
- The get_bill tool is the complete and correct bill. It includes orders from earlier conversations and other screens that you may not remember. Report it as it is. Never suggest it is wrong or send the guest to the front desk about it.
- Place an order as soon as the guest asks, even if they ordered the same thing before. Do not ask whether it was a mistake.
- Answer the guest's latest message. After using a tool, always finish with a short sentence saying what you did or found. Do not bring up earlier messages unless the guest does.
"""


async def post_messages(payload: dict) -> dict:
    """One call to the Messages API. Replaced by a fake in tests."""
    key = os.environ["ANTHROPIC_API_KEY"].strip()
    headers = {
        "x-api-key": key,
        "authorization": f"Bearer {key}",
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    # Only needed for a key that is not tied to one workspace (see .env.example).
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    if workspace:
        headers["anthropic-workspace-id"] = workspace
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(API_URL, headers=headers, json=payload)
    if response.status_code >= 400:
        # The body explains the problem (for example a wrong model name) and never contains the key.
        raise RuntimeError(f"Anthropic API {response.status_code}: {response.text[:300]}")
    return response.json()


async def _run_tool(session, name: str, args: dict, ctx: dict) -> dict:
    """Run one tool for the model. Returns {"ok": ...} or {"error": ...}."""
    room_id = ctx["room_id"]
    booking_id = ctx["booking_id"]
    try:
        if name == "set_light":
            cur = _reported(room_id, "light")
            out = await TOOLS["set_light"](
                session,
                room_id=room_id,
                power=args.get("power", cur.get("power", "on")),
                brightness=int(args.get("brightness", cur.get("brightness", 80))),
                color=args.get("color", cur.get("color", "warm")),
            )
        elif name == "set_central_ac":
            cur = _reported(room_id, "central_ac")
            mode = args.get("mode", "cool")
            if mode in ("eco", "off"):
                target = args.get("target_c", 26)  # the eco set point, whatever it was before
            else:
                target = args.get("target_c", cur.get("target_c", 24))
            target = max(16.0, min(30.0, float(target)))
            out = await TOOLS["set_central_ac"](session, room_id=room_id, target_c=target, mode=mode)
        elif name == "set_bose":
            cur = _reported(room_id, "bose")
            power = args.get("power", "on")
            out = await TOOLS["set_bose"](
                session,
                room_id=room_id,
                power=power,
                volume=int(args.get("volume", cur.get("volume", 25))),
                playing=bool(args.get("playing", power == "on")),
            )
        elif name == "set_curtain":
            out = await TOOLS["set_curtain"](session, room_id=room_id, open_pct=int(args["open_pct"]))
        elif name == "order_room_service":
            if not booking_id:
                return {"error": "no active stay to put this order on"}
            item = str(args.get("item", "")).lower()
            qty = int(args.get("quantity", 1))
            if item not in MENU:
                return {"error": f"'{item}' is not on the menu. Menu: {', '.join(MENU)}"}
            if not 1 <= qty <= MAX_QTY:
                return {"error": f"quantity must be between 1 and {MAX_QTY}"}
            out = await TOOLS["create_service_order"](
                session, item=item, quantity=qty, booking_id=booking_id, room_id=room_id
            )
        elif name == "get_bill":
            return {
                "ok": True,
                "bill": await ctx["bill"](),
                "note": "This is the complete, correct bill, including orders from earlier conversations.",
            }
        elif name == "get_room_state":
            return {"ok": True, "state": get_store(room_id).snapshot()}
        elif name == "check_out":
            if not booking_id:
                return {"error": "no active stay to check out"}
            if not is_checkout_confirmation(ctx["user_text"]):
                return {"error": "the guest has not confirmed yet. Ask them to reply 'yes, check me out'."}
            out = await TOOLS["checkout"](session, booking_id=booking_id, room_id=room_id)
        else:
            return {"error": f"unknown tool {name}"}
    except Exception as e:  # bad values from the model are reported back to it, not raised
        log.warning("tool %s failed: %s", name, e)
        return {"error": str(e)}
    if isinstance(out, dict) and out.get("error"):
        return {"error": str(out["error"])}
    return {"ok": True, "result": out}


def _text_of(blocks) -> str:
    return " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _trim_results(messages: list[dict]) -> list[dict]:
    """A copy of a finished turn, with long tool results cut short, ready to remember."""
    kept = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, list):
            # Hidden "thinking" blocks are tied to the request that produced them. Sending them
            # back later (the system prompt changes with the room state) makes the API refuse.
            content = [b for b in content if b.get("type") not in ("thinking", "redacted_thinking")]
            content = [
                {**b, "content": str(b.get("content", ""))[:TOOL_RESULT_CHARS]} if b.get("type") == "tool_result" else b
                for b in content
            ]
            if not content:
                continue
        kept.append({"role": msg["role"], "content": content})
    return kept


async def respond(session, message: str, *, history_key: str, ctx: dict, system: str) -> dict | None:
    """Ask Claude. Returns {"reply", "actions"}, or None if the rule-based NORA should answer.

    None is only returned when nothing has happened yet, so no action is ever done twice.
    """
    if not within_budget(history_key):
        log.info("NORA hourly limit reached for %s", history_key)
        return None

    ctx = {**ctx, "user_text": message}
    earlier = [m for turn in _history[history_key] for m in turn]
    turn: list[dict] = [{"role": "user", "content": message}]
    actions: list[dict] = []
    last_bill: str | None = None
    reply = ""

    async def ask(extra: list[dict] | None = None) -> dict:
        return await post_messages(
            {
                "model": model_name(),
                "max_tokens": 500,
                "system": system,
                "tools": TOOL_SCHEMAS,
                "messages": earlier + turn + (extra or []),
            }
        )

    finished = False
    for _ in range(MAX_ROUNDS):
        try:
            data = await ask()
        except Exception as e:
            log.warning("NORA could not reach Claude: %s", e)
            if not actions and last_bill is None:
                return None
            reply = "Sorry, I lost my connection part-way. Part of your request may have gone through."
            finished = True
            break

        blocks = data.get("content") or []
        calls = [b for b in blocks if b.get("type") == "tool_use"]
        if data.get("stop_reason") != "tool_use" or not calls:
            reply = _text_of(blocks)
            if reply:
                turn.append({"role": "assistant", "content": blocks})
            finished = True
            break

        turn.append({"role": "assistant", "content": blocks})
        results = []
        for call in calls:
            result = await _run_tool(session, call.get("name", ""), call.get("input") or {}, ctx)
            if result.get("ok") and call.get("name") in ACTION_NAME:
                actions.append({"tool": ACTION_NAME[call["name"]], "result": result.get("result")})
            if result.get("ok") and call.get("name") == "get_bill":
                last_bill = result.get("bill")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.get("id"),
                    "content": str(result),
                    "is_error": "error" in result,
                }
            )
        turn.append({"role": "user", "content": results})

    if not finished:
        reply = "Sorry, that took me too many steps. Could you say it a little differently?"

    if not reply:
        # The model did its work but wrote no answer. Ask once more, without remembering the nudge.
        try:
            data = await ask([{"role": "user", "content": NUDGE}])
            reply = _text_of(data.get("content") or [])
        except Exception as e:
            log.warning("NORA follow-up failed: %s", e)
    if not reply:
        reply = last_bill or "Done."

    if turn[-1]["role"] != "assistant":
        turn.append({"role": "assistant", "content": reply})
    _history[history_key].append(_trim_results(turn))
    return {"reply": reply, "actions": actions}
