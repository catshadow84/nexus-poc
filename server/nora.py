import logging
import os
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .booking_service import get_booking, get_guest
from .models import ServiceOrder
from . import nora_llm
from .nora_tools import MENU, TOOLS
from .state import get_store


log = logging.getLogger("nora")


SYSTEM_PROMPT = """You are NORA, the AI concierge for a NEXUS hotel room.
You are warm, concise, and proactive. You address the guest by name if known.
You can control the room (light, air conditioning, music, curtain), read bookings,
place service orders, and check the guest out.

Rules:
- Confirm before a large action (e.g. checkout).
- Keep replies to 1-3 sentences.
- If a request is outside your tools, apologize briefly and offer an alternative.
- Never invent bookings or orders. Use the tools to verify.
"""


# ---------- rules-based planner (used until a Claude API key is added) ----------

NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
MAX_QTY = 10
MIN_C, MAX_C = 16.0, 30.0
ECO_C = 26.0


def _first_name(full: str) -> str:
    return full.strip().split()[0] if full.strip() else "there"


def _clean(message: str) -> str:
    m = message.lower().replace("’", "'")
    m = re.sub(r"[^\w\s'.]", " ", m)
    return re.sub(r"\s+", " ", m).strip()


def has(m: str, *words: str) -> bool:
    """True if any word or phrase appears as whole words (plurals allowed).

    "light" matches "lights" but not "flight"; "tea" matches "teas" but not "team".
    """
    return any(re.search(rf"\b{re.escape(w)}(?:e?s)?\b", m) for w in words)


def _quantity(m: str, item: str) -> int:
    """How many of an item: '2 coffees', 'two teas', 'a coffee'. Default 1."""
    word = rf"(\d+|{'|'.join(NUMBER_WORDS)})"
    hit = re.search(rf"\b{word}\s+(?:\w+\s+)?{re.escape(item)}", m)
    if not hit:
        return 1
    raw = hit.group(1)
    return int(raw) if raw.isdigit() else NUMBER_WORDS[raw]


def _plural(item: str, qty: int) -> str:
    if qty == 1:
        return item
    return item + ("es" if item.endswith("ch") else "s")


def _menu_item(m: str) -> str | None:
    for item in MENU:
        if has(m, item):
            return item
    return None


def _reported(room_id: str, device: str) -> dict:
    snap = get_store(room_id).snapshot()
    return (snap.get("devices", {}).get(device, {}).get("reported")) or {}


def _plan(reply, calls=None, special=None) -> dict:
    return {"reply": reply, "calls": calls or [], "special": special}


def _fallback_plan(
    message: str,
    guest_name: str | None = None,
    guest_prefs: dict | None = None,
    room_id: str = "room1",
) -> dict:
    m = _clean(message)
    name = _first_name(guest_name) if guest_name else None
    prefs = guest_prefs or {}

    def addr(text: str) -> str:
        return f"{name}, {text}" if name else text[0].upper() + text[1:]

    # ---- who am I / preferences ----

    if has(m, "who am i", "do you know me", "my name", "remember me"):
        if name:
            parts = []
            light = prefs.get("light") or {}
            if light:
                parts.append(f"light {light.get('brightness', '?')}% {light.get('color', '')}".strip())
            ac = prefs.get("central_ac") or prefs.get("thermostat") or {}
            if ac:
                parts.append(f"air conditioning {ac.get('target_c', '?')}°C")
            curtain = prefs.get("curtain") or {}
            if curtain:
                parts.append(f"curtain {curtain.get('open_pct', '?')}%")
            summary = ", ".join(parts) if parts else "no preferences on file"
            return _plan(f"You're {guest_name}. Saved preferences: {summary}.")
        return _plan("I don't have an active booking for you yet.")

    if has(m, "what do i like", "my preferences", "my settings"):
        lines = [
            f"{dev}: " + ", ".join(f"{k}={val}" for k, val in v.items())
            for dev, v in prefs.items()
            if isinstance(v, dict)
        ]
        return _plan("\n".join(lines) if lines else "You don't have any preferences saved yet.")

    # ---- check-out (always confirmed with an explicit sentence) ----

    wants_checkout = has(m, "check me out", "check out", "checkout", "end my stay", "finish my stay")
    if wants_checkout and has(m, "what time", "when", "until", "by what time"):
        return _plan(None, special="checkout_time")
    if wants_checkout and has(m, "late", "early", "extend", "extension"):
        return _plan(addr("late or early check-out has to be arranged with the front desk. Please ask them directly."))
    if wants_checkout and has(m, "yes", "yeah", "yep", "confirm", "confirmed", "sure", "please do"):
        return _plan(addr("checking you out now. Thank you for staying with us!"), [("checkout", {})])
    if wants_checkout:
        return _plan(
            addr("this ends your stay and takes you to your receipt. Reply \"yes, check me out\" to confirm.")
        )

    # ---- bill, menu, help ----

    if has(m, "bill", "receipt", "how much", "what do i owe", "my total", "charges", "my charges"):
        return _plan(None, special="bill")
    if has(m, "menu", "what can i order", "what do you have", "hungry", "drinks"):
        return _plan(None, special="menu")
    if has(m, "help", "what can you do", "what do you do"):
        return _plan(HELP)

    # ---- room service ----

    item = _menu_item(m)
    order_words = ("order", "bring", "send", "get me", "i want", "i'd like", "i would like",
                   "can i have", "could i have", "i'll have", "please", "room service")
    if item and has(m, *order_words):
        qty = _quantity(m, item)
        if qty > MAX_QTY:
            return _plan(addr(f"I can order up to {MAX_QTY} at a time. How many would you like?"))
        return _plan(
            addr(f"ordering {qty} {_plural(item, qty)}. It'll be up shortly."),
            [("create_service_order", {"item": item, "quantity": qty})],
        )
    if has(m, "order", "room service", "food", "snack", "something to eat", "something to drink"):
        return _plan(None, special="menu")

    # ---- scenes ----

    if has(m, "goodnight", "good night", "going to sleep", "bedtime"):
        return _plan(
            addr("goodnight. Light off, curtain closed, air conditioning to 19."),
            [
                ("set_light", {"power": "off", "brightness": 0, "color": "neutral"}),
                ("set_curtain", {"open_pct": 0}),
                ("set_central_ac", {"target_c": 19, "mode": "cool"}),
            ],
        )
    if has(m, "good morning", "wake up", "waking up"):
        return _plan(
            addr("good morning. Waking the room up."),
            [
                ("set_light", {"power": "on", "brightness": 60, "color": "warm"}),
                ("set_curtain", {"open_pct": 70}),
                ("set_central_ac", {"target_c": 22, "mode": "cool"}),
            ],
        )

    # ---- air conditioning ----

    ac_words = ("ac", "a c", "aircon", "air con", "air conditioning", "air conditioner", "air-conditioning")
    if has(m, "eco", "eco mode", "energy saving", "save energy", "going out", "heading out", "leaving the room", "i'm out"):
        return _plan(
            addr("eco mode on. I'll keep the air conditioning low while you're out."),
            [("set_central_ac", {"target_c": ECO_C, "mode": "eco"})],
        )
    if has(m, *ac_words) and has(m, "off", "stop", "switch off", "turn off"):
        return _plan(addr("air conditioning off."), [("set_central_ac", {"target_c": ECO_C, "mode": "off"})])

    if has(m, "curtain", "blind", "shade"):
        nums = re.findall(r"(\d+)", m)
        if nums:
            pct = max(0, min(100, int(nums[0])))
        elif has(m, "close"):
            pct = 0
        elif has(m, "open"):
            pct = 100
        else:
            pct = (prefs.get("curtain") or {}).get("open_pct", 50)
        return _plan(addr(f"curtain to {pct}%."), [("set_curtain", {"open_pct": pct})])

    if has(m, *ac_words, "cold", "freezing", "chilly", "hot", "warmer", "cooler", "colder",
           "stuffy", "temperature", "degrees", "thermostat", "warm me"):
        current = float(_reported(room_id, "central_ac").get("target_c") or 22.0)
        default_pref = (prefs.get("central_ac") or prefs.get("thermostat") or {}).get("target_c")
        nums = re.findall(r"(\d+(?:\.\d+)?)", m)
        if nums:
            target = float(nums[0])
        elif has(m, "colder", "cooler", "hot", "stuffy"):
            target = current - 2
        elif has(m, "cold", "freezing", "chilly", "warmer", "warm me"):
            target = current + 2
        elif default_pref is not None:
            target = float(default_pref)
        else:
            target = current
        clamped = max(MIN_C, min(MAX_C, target))
        note = "" if clamped == target else f" ({target:g}° is outside the safe range, so I used {clamped:g}°)"
        return _plan(
            addr(f"setting the air conditioning to {clamped:g}°C{note}."),
            [("set_central_ac", {"target_c": clamped, "mode": "cool"})],
        )

    # ---- light ----

    if has(m, "light", "lamp", "dark", "dim", "dimmer", "darker", "brighter", "bright"):
        lp = prefs.get("light") or {}
        if has(m, "off"):
            return _plan(addr("turning the lights off."),
                         [("set_light", {"power": "off", "brightness": 0, "color": "neutral"})])
        if has(m, "dim", "dimmer", "darker", "softer"):
            return _plan(addr("dimming the lights."),
                         [("set_light", {"power": "on", "brightness": 30, "color": lp.get("color", "warm")})])
        if has(m, "brighter", "bright", "dark"):
            return _plan(addr("brighter lights coming up."),
                         [("set_light", {"power": "on", "brightness": 100, "color": lp.get("color", "neutral")})])
        if has(m, "cool"):
            return _plan(addr("setting the light cool."),
                         [("set_light", {"power": "on", "brightness": 100, "color": "cool"})])
        if has(m, "warm"):
            return _plan(addr("setting the light warm."),
                         [("set_light", {"power": "on", "brightness": 60, "color": "warm"})])
        return _plan(addr("lights on."),
                     [("set_light", {"power": "on", "brightness": lp.get("brightness", 80),
                                     "color": lp.get("color", "warm")})])

    # ---- music ----

    if has(m, "music", "speaker", "volume", "bose", "song", "play", "pause", "louder", "quieter", "turn it up", "turn it down", "turn up", "turn down"):
        bose = _reported(room_id, "bose")
        vol_now = int(bose.get("volume", 20))
        nums = re.findall(r"(\d+)", m)
        if has(m, "off", "stop"):
            return _plan(addr("turning the music off."),
                         [("set_bose", {"power": "off", "volume": vol_now, "playing": False})])
        if has(m, "pause"):
            return _plan(addr("pausing the music."),
                         [("set_bose", {"power": "on", "volume": vol_now, "playing": False})])
        if has(m, "louder", "volume up", "turn it up", "turn up", "turn the music up"):
            vol = min(100, vol_now + 10)
        elif has(m, "quieter", "volume down", "turn it down", "turn down", "turn the music down"):
            vol = max(0, vol_now - 10)
        elif nums:
            vol = max(0, min(100, int(nums[0])))
        else:
            vol = vol_now if bose.get("power") == "on" else 25
        return _plan(addr(f"playing music at volume {vol}."),
                     [("set_bose", {"power": "on", "volume": vol, "playing": True})])

    # ---- door ----

    if has(m, "door", "unlock", "lock", "locked", "key"):
        return _plan(addr("tap Unlock on the Door card of your room screen, or type your door code on the keypad. I can't open the door myself yet."))

    # ---- room status ----

    if has(m, "status", "state", "currently") or (
        has(m, "what", "how", "is") and has(m, "room", "light", "ac", "temperature", "curtain", "music")
    ):
        light = _reported(room_id, "light")
        ac = _reported(room_id, "central_ac")
        curtain = _reported(room_id, "curtain")
        bose = _reported(room_id, "bose")
        light_txt = f"on at {light.get('brightness')}%" if light.get("power") == "on" else "off"
        reply = (
            f"the light is {light_txt}. "
            f"The air conditioning is in {ac.get('mode', '?')} mode at {ac.get('current_c', '?')}°C, target {ac.get('target_c', '?')}°C. "
            f"Curtain is {curtain.get('open_pct', '?')}% open. "
            f"Music is {'playing' if bose.get('playing') else 'off or paused'}."
        )
        return _plan(addr(reply))

    return _plan(f"{name}, {HELP}" if name else HELP)


HELP = (
    "I can change the light, air conditioning, music and curtain, order room service, "
    "show your bill, and check you out. What would you like?"
)

FRIENDLY_ERRORS = {
    "no active booking to attach this order to": "I can only place orders during an active stay.",
    "booking not found": "I couldn't find your booking.",
}


def _error_of(entry: dict) -> str | None:
    """The error of one tool entry: raised, or returned as {"error": ...}."""
    if entry.get("error"):
        return str(entry["error"])
    result = entry.get("result")
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    return None


def _failure_text(results: list[dict]) -> str | None:
    """A sentence about the first failed action, or None if everything worked."""
    for entry in results:
        err = _error_of(entry)
        if err:
            return FRIENDLY_ERRORS.get(err, f"Something went wrong: {err}.")
    return None


def _money(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def _checkout_hour() -> int:
    try:
        hour = int(os.getenv("CHECKOUT_HOUR", "12"))
    except ValueError:
        return 12
    return hour if 0 <= hour <= 23 else 12


async def _special_reply(session, special: str, booking) -> str:
    if booking is None:
        return "I need an active stay for that. Please check in first."
    currency = booking.currency or "USD"
    if special == "menu":
        items = ", ".join(f"{k} {_money(v, currency)}" for k, v in MENU.items())
        return f"Room service menu: {items}. Just say, for example, \"order two coffees\"."
    if special == "checkout_time":
        hour = f"{_checkout_hour():02d}:00"
        if booking.planned_check_out:
            return f"Check-out is on {booking.planned_check_out.strftime('%a %d %b')} at {hour}."
        return f"Check-out is at {hour} on your departure day."
    if special == "bill":
        rows = (await session.execute(
            select(ServiceOrder).where(ServiceOrder.booking_id == booking.id)
        )).scalars().all()
        lines = []
        if booking.total_cents:
            lines.append(f"Room: {_money(booking.total_cents, currency)}")
        if rows:
            total = sum(o.quantity * o.unit_price_cents for o in rows)
            items = ", ".join(f"{o.quantity}x {o.item}" for o in rows)
            lines.append(f"Room service: {items} = {_money(total, currency)}")
        else:
            lines.append("No room service orders yet")
        return ". ".join(lines) + ". The full receipt appears when you check out."
    return HELP


# ---------- public API ----------

async def handle_message(
    session,
    session_id: str,
    message: str,
    booking_id: str | None = None,
    room_id: str = "room1",
) -> dict:
    guest_name = None
    guest_prefs = {}
    booking = None
    if booking_id:
        booking = await get_booking(session, booking_id)
        if booking and booking.status == "CHECKED_IN":
            guest = await get_guest(session, booking.guest_id)
            if guest:
                guest_name = guest.name
                guest_prefs = guest.preferences or {}
            room_id = booking.room_id  # trust the booking over the query param
        else:
            booking = None

    if nora_llm.enabled():
        currency = (booking.currency if booking else None) or "USD"
        checkout_text = await _special_reply(session, "checkout_time", booking) if booking else ""
        answer = await nora_llm.respond(
            session,
            message,
            history_key=booking.id if booking else f"session:{session_id}",
            ctx={
                "room_id": room_id,
                "booking_id": booking.id if booking else None,
                "bill": lambda: _special_reply(session, "bill", booking),
            },
            system=nora_llm.system_prompt(guest_name, room_id, booking, currency, checkout_text),
        )
        if answer is not None:
            return {
                "reply": answer["reply"],
                "actions": answer["actions"],
                "session_id": session_id,
                "guest_name": guest_name,
                "room_id": room_id,
                "booking_id": booking_id,
                "engine": "claude",
            }

    plan = _fallback_plan(message, guest_name, guest_prefs, room_id)

    reply = plan["reply"]
    if plan.get("special"):
        reply = await _special_reply(session, plan["special"], booking)

    results = []
    for tool_name, args in plan["calls"]:
        fn = TOOLS.get(tool_name)
        if not fn:
            continue
        call_args = dict(args)
        call_args["room_id"] = room_id
        if booking_id and "booking_id" not in call_args:
            call_args["booking_id"] = booking_id
        try:
            result = await fn(session, **call_args)
            results.append({"tool": tool_name, "result": result})
        except Exception as e:
            log.exception("tool %s failed", tool_name)
            results.append({"tool": tool_name, "error": str(e)})

    failure = _failure_text(results)
    if failure:
        reply = f"Sorry, I couldn't do that. {failure}"
        results = [r for r in results if _error_of(r) is None]

    return {
        "reply": reply,
        "actions": results,
        "session_id": session_id,
        "guest_name": guest_name,
        "room_id": room_id,
        "booking_id": booking_id,
        "engine": "rules",
    }
