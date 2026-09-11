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

def _fallback_plan(message: str) -> dict:
    m = message.lower().strip()
    calls: list[tuple[str, dict]] = []

    if any(k in m for k in ("goodnight", "good night", "going to sleep")):
        calls = [
            ("set_light", {"power": "off", "brightness": 0, "color": "neutral"}),
            ("set_curtain", {"open_pct": 0}),
            ("set_thermostat", {"target_c": 19, "mode": "cool"}),
        ]
        return {"reply": "Goodnight. Light off, curtain closed, thermostat to 19.", "calls": calls}

    if "good morning" in m or "wake" in m:
        calls = [
            ("set_light", {"power": "on", "brightness": 60, "color": "warm"}),
            ("set_curtain", {"open_pct": 70}),
            ("set_thermostat", {"target_c": 22, "mode": "cool"}),
        ]
        return {"reply": "Good morning. Waking the room up.", "calls": calls}

    if "curtain" in m or "blind" in m or "shade" in m:
        nums = re.findall(r"(\d+)", m)
        if nums:
            pct = int(nums[0])
        elif "close" in m:
            pct = 0
        elif "open" in m:
            pct = 100
        else:
            pct = 50
        return {"reply": f"Curtain at {pct}%.", "calls": [("set_curtain", {"open_pct": pct})]}

    if any(k in m for k in ("cold", "freezing", "warm me", "hot", "temperature", "degrees", "thermostat")):
        state = store.snapshot()
        current = (
            (state.get("devices", {}).get("thermostat", {}).get("reported") or {})
            .get("target_c", 22.0)
        )
        nums = re.findall(r"(\d+(?:\.\d+)?)", m)
        if nums:
            target = float(nums[0])
        elif "cold" in m or "warm" in m:
            target = current + 2
        elif "hot" in m:
            target = current - 2
        else:
            target = current
        return {
            "reply": f"Setting the thermostat to {target}°C.",
            "calls": [("set_thermostat", {"target_c": target, "mode": "cool"})],
        }

    if any(k in m for k in ("light", "lamp", "dark", "bright")):
        if "off" in m or "dark" in m:
            calls = [("set_light", {"power": "off", "brightness": 0, "color": "neutral"})]
            return {"reply": "Turning the lights off.", "calls": calls}
        if "cool" in m:
            calls = [("set_light", {"power": "on", "brightness": 100, "color": "cool"})]
            return {"reply": "Setting the light to cool.", "calls": calls}
        if "warm" in m:
            calls = [("set_light", {"power": "on", "brightness": 60, "color": "warm"})]
            return {"reply": "Setting the light to warm.", "calls": calls}
        if "off" not in m:
            calls = [("set_light", {"power": "on", "brightness": 80, "color": "warm"})]
            return {"reply": "Lights on.", "calls": calls}

    if any(k in m for k in ("coffee", "tea", "water", "food", "order", "room service", "snack", "sandwich")):
        item = "coffee"
        for cand in ("coffee", "tea", "water", "sandwich", "snack"):
            if cand in m:
                item = cand
                break
        return {
            "reply": f"Ordering {item} for you. It'll be up shortly.",
            "calls": [("create_service_order", {"item": item, "quantity": 1})],
        }

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
        return {"reply": reply, "calls": []}

    return {
        "reply": "I can control the light, thermostat, and curtain, place service orders, and check you out. What would you like?",
        "calls": [],
    }


# ---------- public API ----------

async def handle_message(
    session: AsyncSession,
    session_id: str,
    message: str,
    booking_id: str | None = None,
) -> dict:
    """Main entry point.

    Today: uses the rules-based fallback.
    Later: swap the line below for a Claude tool-use loop. Everything else
    in this function stays identical.
    """
    plan = _fallback_plan(message)

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
    }