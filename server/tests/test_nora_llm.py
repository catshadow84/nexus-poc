import copy
import json

import pytest
from sqlalchemy import select

from server import nora_llm
from server.booking_service import check_in
from server.models import ServiceOrder
from server.nora import handle_message


def text(t):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": t}]}


def tool(name, args=None, call_id="t1"):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args or {}}],
    }


class FakeClaude:
    def __init__(self):
        self.queue = []
        self.payloads = []

    async def __call__(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret")
    monkeypatch.setattr(nora_llm, "post_messages", fake)
    return fake


async def stay(session, make_booking):
    booking = await make_booking(room_id="room1")
    await check_in(session, booking)
    return booking


async def say(session, booking, message):
    return await handle_message(session, "s", message, booking_id=booking.id)


async def test_without_a_key_the_rule_based_nora_answers(session, make_booking):
    booking = await stay(session, make_booking)
    out = await say(session, booking, "order 2 coffees")
    assert out["engine"] == "rules"
    assert "ordering 2 coffees" in out["reply"]


async def test_the_model_can_change_the_room(session, make_booking, claude, published):
    booking = await stay(session, make_booking)
    before = len(published)
    claude.queue = [tool("set_light", {"power": "on", "brightness": 40}), text("Dimmed to 40%.")]
    out = await say(session, booking, "make it cosy")
    assert out["engine"] == "claude"
    assert out["reply"] == "Dimmed to 40%."
    assert [a["tool"] for a in out["actions"]] == ["set_light"]
    assert any("light" in topic for topic, _ in published[before:])


async def test_check_out_needs_the_guests_own_confirmation(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("check_out"), text("Please reply yes, check me out.")]
    out = await say(session, booking, "I'm done here")
    await session.refresh(booking)
    assert booking.status == "CHECKED_IN"
    assert out["actions"] == []
    second_call = claude.payloads[1]["messages"][-1]["content"][0]
    assert second_call["is_error"] is True


async def test_a_confirmed_check_out_goes_through(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("check_out"), text("Goodbye, thank you!")]
    out = await say(session, booking, "yes, check me out")
    await session.refresh(booking)
    assert booking.status == "CHECKED_OUT"
    assert [a["tool"] for a in out["actions"]] == ["checkout"]
    assert out["booking_id"] == booking.id


async def test_only_menu_items_can_be_ordered(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("order_room_service", {"item": "pizza"}), text("Sorry, no pizza.")]
    out = await say(session, booking, "a pizza please")
    assert out["actions"] == []
    assert (await session.execute(select(ServiceOrder))).scalars().all() == []


async def test_too_many_items_are_refused(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("order_room_service", {"item": "tea", "quantity": 11}), text("Too many.")]
    await say(session, booking, "eleven teas")
    assert (await session.execute(select(ServiceOrder))).scalars().all() == []


async def test_the_model_cannot_pick_the_booking_or_room(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [
        tool("order_room_service", {"item": "tea", "quantity": 1, "booking_id": "someone-else", "room_id": "room9"}),
        text("Tea is on its way."),
    ]
    await say(session, booking, "a tea")
    [order] = (await session.execute(select(ServiceOrder))).scalars().all()
    assert order.booking_id == booking.id


async def test_if_claude_is_unreachable_the_rules_take_over(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [RuntimeError("no internet")]
    out = await say(session, booking, "order a coffee")
    assert out["engine"] == "rules"
    assert "ordering 1 coffee" in out["reply"]
    assert len((await session.execute(select(ServiceOrder))).scalars().all()) == 1


async def test_a_failure_after_an_action_does_not_repeat_it(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("order_room_service", {"item": "coffee"}), RuntimeError("dropped")]
    out = await say(session, booking, "a coffee")
    assert out["engine"] == "claude"
    assert "lost my connection" in out["reply"]
    assert [a["tool"] for a in out["actions"]] == ["create_service_order"]
    assert len((await session.execute(select(ServiceOrder))).scalars().all()) == 1


async def test_the_conversation_is_remembered(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [text("Hello Sam!"), text("You said hello.")]
    await say(session, booking, "hello")
    await say(session, booking, "what did I say?")
    roles = [m["role"] for m in claude.payloads[1]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert claude.payloads[1]["messages"][0]["content"] == "hello"


async def test_the_prompt_has_the_menu_and_no_secret(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [text("Hi!")]
    await say(session, booking, "hi")
    payload = claude.payloads[0]
    assert "coffee 4.50" in payload["system"]
    assert "sk-ant-test-secret" not in json.dumps(payload)
    assert payload["model"] == "claude-haiku-5-5"


async def test_the_model_name_can_be_changed(session, make_booking, claude, monkeypatch):
    monkeypatch.setenv("NORA_MODEL", "claude-sonnet-5-5")
    booking = await stay(session, make_booking)
    claude.queue = [text("Hi!")]
    await say(session, booking, "hi")
    assert claude.payloads[0]["model"] == "claude-sonnet-5-5"


async def test_rules_mode_ignores_the_key(session, make_booking, claude, monkeypatch):
    monkeypatch.setenv("NORA_MODE", "rules")
    booking = await stay(session, make_booking)
    out = await say(session, booking, "order a tea")
    assert out["engine"] == "rules"
    assert claude.payloads == []


async def test_an_hourly_limit_sends_guests_to_the_rules(session, make_booking, claude, monkeypatch):
    monkeypatch.setenv("NORA_MAX_PER_HOUR", "1")
    booking = await stay(session, make_booking)
    claude.queue = [text("First answer.")]
    assert (await say(session, booking, "hi"))["engine"] == "claude"
    assert (await say(session, booking, "order a tea"))["engine"] == "rules"


async def test_the_bill_tool_reads_the_real_bill(session, make_booking, claude):
    booking = await stay(session, make_booking)
    session.add(ServiceOrder(booking_id=booking.id, item="coffee", quantity=2, unit_price_cents=450))
    await session.commit()
    claude.queue = [tool("get_bill"), text("Your coffees come to 9.00.")]
    out = await say(session, booking, "what do I owe?")
    result = claude.payloads[1]["messages"][-1]["content"][0]["content"]
    assert "2x coffee" in result and "9.00" in result
    assert out["actions"] == []


@pytest.mark.parametrize(
    "message, expected",
    [
        ("yes, check me out", True),
        ("Yes please check out", True),
        ("confirm checkout", True),
        ("check me out", False),
        ("yes", False),
        ("I'm done", False),
    ],
)
def test_check_out_confirmation_wording(message, expected):
    assert nora_llm.is_checkout_confirmation(message) is expected


async def test_an_empty_answer_after_a_tool_is_asked_for_again(session, make_booking, claude):
    booking = await stay(session, make_booking)
    session.add(ServiceOrder(booking_id=booking.id, item="coffee", quantity=2, unit_price_cents=450))
    await session.commit()
    empty = {"stop_reason": "end_turn", "content": []}
    claude.queue = [tool("get_bill"), empty, text("You owe 9.00 USD so far.")]
    out = await say(session, booking, "what do I owe?")
    assert out["reply"] == "You owe 9.00 USD so far."
    assert "Now answer the guest" in json.dumps(claude.payloads[2]["messages"][-1])


async def test_if_it_stays_empty_the_bill_text_is_shown(session, make_booking, claude):
    booking = await stay(session, make_booking)
    session.add(ServiceOrder(booking_id=booking.id, item="tea", quantity=1, unit_price_cents=400))
    await session.commit()
    empty = {"stop_reason": "end_turn", "content": []}
    claude.queue = [tool("get_bill"), empty, empty]
    out = await say(session, booking, "my bill?")
    assert "1x tea" in out["reply"]
    # the nudge is not remembered, and the stored turn is well-formed
    remembered = nora_llm._history[booking.id][-1]
    assert remembered[-1]["role"] == "assistant"
    assert "Now answer the guest" not in json.dumps(remembered)


async def test_the_next_message_sees_what_nora_did(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("set_central_ac", {"target_c": 28}), text("Warmer: 28."), text("Yes, I set 28.")]
    await say(session, booking, "I'm cold")
    await say(session, booking, "what did you change?")
    sent = json.dumps(claude.payloads[2]["messages"])
    assert "tool_use" in sent and "tool_result" in sent


async def test_eco_uses_the_eco_set_point_not_the_old_target(session, make_booking, claude, published):
    from server.state import get_store

    booking = await stay(session, make_booking)
    get_store("room1").set_reported("central_ac", {"target_c": 28.0, "mode": "cool"})
    before = len(published)
    claude.queue = [tool("set_central_ac", {"mode": "eco"}), text("Eco mode on.")]
    await say(session, booking, "I'm heading out")
    sent = [payload for topic, payload in published[before:] if "central_ac" in topic]
    assert sent and sent[-1]["value"]["target_c"] == 26.0 and sent[-1]["value"]["mode"] == "eco"


async def test_hidden_thinking_blocks_are_not_sent_back_later(session, make_booking, claude):
    booking = await stay(session, make_booking)
    thinking = {"type": "thinking", "thinking": "hmm", "signature": "abc"}
    claude.queue = [
        {"stop_reason": "end_turn", "content": [thinking, {"type": "text", "text": "Hello Sam!"}]},
        text("Still here."),
    ]
    await say(session, booking, "hello")
    await say(session, booking, "are you there?")
    assert "thinking" not in json.dumps(claude.payloads[1]["messages"])
    assert "Hello Sam!" in json.dumps(claude.payloads[1]["messages"])


async def test_thinking_is_kept_inside_one_exchange(session, make_booking, claude):
    booking = await stay(session, make_booking)
    thinking = {"type": "thinking", "thinking": "hmm", "signature": "abc"}
    first = tool("get_room_state")
    first["content"].insert(0, thinking)
    claude.queue = [first, text("All good.")]
    await say(session, booking, "status?")
    assert "thinking" in json.dumps(claude.payloads[1]["messages"])


async def test_the_model_is_told_the_bill_is_complete(session, make_booking, claude):
    booking = await stay(session, make_booking)
    claude.queue = [tool("get_bill"), text("Here it is.")]
    await say(session, booking, "what do I owe?")
    assert "complete and correct bill" in claude.payloads[0]["system"]
    assert "Place an order as soon as" in claude.payloads[0]["system"]
    assert "complete, correct bill" in claude.payloads[1]["messages"][-1]["content"][0]["content"]
