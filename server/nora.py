from .booking_service import get_booking, get_guest
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from .nora_tools import TOOLS
from .state import store


log = logging.getLogger("nora")


SYSTEM_PROMPT = """You are NORA, the AI concierge for a NEXUS hotel room.
You are warm, concise, and proactive. You address the guest by name if known.
You can control the room (light, thermostat, curtain), read bookings, place
service orders, and check the guest out.

Rules:
- Confirm before a large action (e.g. checkout).
- Keep replies to 1-3 sentences.
- If a request is outside your tools, apologize briefly and offer an alternative.
- Never invent bookings or orders. Use the tools to verify.
"""


# ---------- rules-based fallback (until Claude API key arrives) ----------

def _first_name(full: str) -> str:
    return full.strip().split()[0] if full.strip() else "there"


def _fallback_plan(
    message: str,
    guest_name: str | None = None,
    guest_prefs: dict | None = None,
) -> dict:
    m = message.lower().strip()
    name = _first_name(guest_name) if guest_name else None
    prefs = guest_prefs or {}
    calls: list[tuple[str, dict]] = []

    def addr(text: str) -> str:
        return f"{name}, {text}" if name else text[0].upper() + text[1:]

    # ---- identity / memory intents ----

    if any(k in m for k in ("who am i", "do you know me", "my name", "remember me")):
        if name:
            prefs_summary = []
            l = prefs.get("light") or {}
            if l:
                prefs_summary.append(
                    f"light {l.get('brightness', '?')}% {l.get('color', '')}".strip()
                )
            t = prefs.get("thermostat") or {}
            if t:
                prefs_summary.append(f"thermostat {t.get('target_c', '?')}°C")
            c = prefs.get("curtain") or {}
            if c:
                prefs_summary.append(f"curtain {c.get('open_pct', '?')}%")
            summary = ", ".join(prefs_summary) if prefs_summary else "no preferences on file"
            return {"reply": f"You're {guest_name}. Saved preferences: {summary}.", "calls": []}
        return {"reply": "I don't have an active booking for you yet.", "calls": []}

    if any(k in m for k in ("what do i like", "my preferences", "my settings")):
        if prefs:
            lines = []
            for dev, v in prefs.items():
                if isinstance(v, dict):
                    lines.append(f"{dev}: " + ", ".join(f"{k}={val}" for k, val in v.items()))
            return {"reply": "\n".join(lines), "calls": []}
        return {"reply": "You don't have any preferences saved yet.", "calls": []}

    # ---- scenes ----

    if any(k in m for k in ("goodnight", "good night", "going to sleep")):
        calls = [
            ("set_light", {"power": "off", "brightness": 0, "color": "neutral"}),
            ("set_curtain", {"open_pct": 0}),
            ("set_thermostat", {"target_c": 19, "mode": "cool"}),
        ]
        return {"reply": addr("goodnight — light off, curtain closed, thermostat to 19."), "calls": calls}

    if "good morning" in m or "wake" in m:
        calls = [
            ("set_light", {"power": "on", "brightness": 60, "color": "warm"}),
            ("set_curtain", {"open_pct": 70}),
            ("set_thermostat", {"target_c": 22, "mode": "cool"}),
        ]
        return {"reply": addr("good morning — waking the room up."), "calls": calls}

    # ---- device control (uses guest prefs as defaults) ----

    if any(k in m for k in ("curtain", "blind", "shade")):
        nums = re.findall(r"(\d+)", m)
        if nums:
            pct = int(nums[0])
        elif "close" in m:
            pct = 0
        elif "open" in m:
            pct = 100
        else:
            pct = (prefs.get("curtain") or {}).get("open_pct", 50)
        return {"reply": addr(f"curtain to {pct}%."), "calls": [("set_curtain", {"open_pct": pct})]}

    if any(k in m for k in ("cold", "freezing", "warm me", "hot", "temperature", "degrees", "thermostat")):
        state = store.snapshot()
        current = (state.get("devices", {}).get("thermostat", {}).get("reported") or {}).get("target_c", 22.0)
        default_pref = (prefs.get("thermostat") or {}).get("target_c")
        nums = re.findall(r"(\d+(?:\.\d+)?)", m)
        if nums:
            target = float(nums[0])
        elif "cold" in m or "warm" in m:
            target = current + 2
        elif "hot" in m:
            target = current - 2
        elif default_pref is not None:
            target = float(default_pref)
        else:
            target = current
        return {
            "reply": addr(f"setting the thermostat to {target}°C."),
            "calls": [("set_thermostat", {"target_c": target, "mode": "cool"})],
        }

    if any(k in m for k in ("light", "lamp", "dark", "bright")):
        lp = prefs.get("light") or {}
        if "off" in m or "dark" in m:
            return {"reply": addr("turning the lights off."),
                    "calls": [("set_light", {"power": "off", "brightness": 0, "color": "neutral"})]}
        if "cool" in m:
            return {"reply": addr("setting the light cool."),
                    "calls": [("set_light", {"power": "on", "brightness": 100, "color": "cool"})]}
        if "warm" in m:
            return {"reply": addr("setting the light warm."),
                    "calls": [("set_light", {"power": "on", "brightness": 60, "color": "warm"})]}
        # "turn on the lights" — use guest prefs
        return {"reply": addr("lights on."),
                "calls": [("set_light", {
                    "power": "on",
                    "brightness": lp.get("brightness", 80),
                    "color": lp.get("color", "warm"),
                })]}

    # ---- service ----

    if any(k in m for k in ("coffee", "tea", "water", "food", "order", "room service", "snack", "sandwich")):
        item = "coffee"
        for cand in ("coffee", "tea", "water", "sandwich", "snack"):
            if cand in m:
                item = cand
                break
        return {
            "reply": addr(f"ordering {item} — it'll be up shortly."),
            "calls": [("create_service_order", {"item": item, "quantity": 1})],
        }

    # ---- state ----

    if any(k in m for k in ("how", "what", "state", "status", "currently")):
        s = store.snapshot()
        dev = s.get("devices", {})
        light = dev.get("light", {}).get("reported") or {}
        thermo = dev.get("thermostat", {}).get("reported") or {}
        cur = dev.get("curtain", {}).get("reported") or {}
        reply = (
            f"Light is {light.get('power', 'unknown')}"
            f"{(' at ' + str(light.get('brightness')) + '%') if light.get('power') == 'on' else ''}. "
            f"Thermostat at {thermo.get('current_c', '?')}°C, target {thermo.get('target_c', '?')}°C. "
            f"Curtain {cur.get('open_pct', '?')}% open."
        )
        return {"reply": addr(reply), "calls": []}

    default = "I can control the light, thermostat, and curtain, place service orders, and check you out. What would you like?"
    return {"reply": f"{name}, {default[0].lower() + default[1:]}" if name else default, "calls": []}


# ---------- public API ----------

async def handle_message(
    session: AsyncSession,
    session_id: str,
    message: str,
    booking_id: str | None = None,
) -> dict:
    # load guest context if a booking is attached
    guest_name: str | None = None
    guest_prefs: dict = {}
    if booking_id:
        booking = await get_booking(session, booking_id)
        if booking and booking.status == "CHECKED_IN":
            guest = await get_guest(session, booking.guest_id)
            if guest:
                guest_name = guest.name
                guest_prefs = guest.preferences or {}

    plan = _fallback_plan(message, guest_name, guest_prefs)

    results = []
    for tool_name, args in plan["calls"]:
        fn = TOOLS.get(tool_name)
        if not fn:
            log.warning("unknown tool %s", tool_name)
            continue
        try:
            result = await fn(session, **args)
            results.append({"tool": tool_name, "result": result})
        except Exception as e:
            log.exception("tool %s failed", tool_name)
            results.append({"tool": tool_name, "error": str(e)})

    return {
        "reply": plan["reply"],
        "actions": results,
        "session_id": session_id,
        "guest_name": guest_name,
    }