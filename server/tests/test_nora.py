from datetime import datetime

import pytest
from sqlalchemy import select

from server.booking_service import check_in
from server.models import ServiceOrder
from server.nora import _fallback_plan, handle_message
from server.state import get_store


def plan(message, name="Sam"):
    return _fallback_plan(message, name)


def calls(message):
    return plan(message)["calls"]


# ---------- the planner ----------


@pytest.mark.parametrize(
    "message",
    ["when is my flight", "the team is here", "show me the photo", "what a waterfall", "hello"],
)
def test_words_inside_other_words_do_nothing(message):
    assert calls(message) == []


def test_too_dark_turns_the_light_up_not_off():
    [(tool, args)] = calls("it's too dark in here")
    assert tool == "set_light" and args["power"] == "on" and args["brightness"] == 100


def test_lights_off_still_turns_them_off():
    [(tool, args)] = calls("please turn off the lights")
    assert tool == "set_light" and args["power"] == "off"


@pytest.mark.parametrize(
    "message, item, qty",
    [
        ("order 2 coffees", "coffee", 2),
        ("two teas please", "tea", 2),
        ("bring me a sandwich", "sandwich", 1),
        ("can I have a coffee", "coffee", 1),
        ("I'd like 3 sandwiches", "sandwich", 3),
    ],
)
def test_orders_read_the_item_and_quantity(message, item, qty):
    assert calls(message) == [("create_service_order", {"item": item, "quantity": qty})]


def test_an_unknown_item_shows_the_menu_instead_of_ordering_coffee():
    p = plan("order pizza")
    assert p["calls"] == [] and p["special"] == "menu"


def test_too_many_items_is_refused():
    p = plan("order 50 coffees")
    assert p["calls"] == [] and "10" in p["reply"]


def test_check_out_needs_an_explicit_yes():
    asked = plan("check me out")
    assert asked["calls"] == [] and "yes, check me out" in asked["reply"]
    assert plan("yes, check me out")["calls"] == [("checkout", {})]
    assert plan("what time is checkout")["special"] == "checkout_time"
    assert plan("late checkout please")["calls"] == []


def test_leaving_the_room_switches_the_air_conditioning_to_eco():
    assert calls("I'm leaving the room") == [("set_central_ac", {"target_c": 26.0, "mode": "eco"})]


def test_air_conditioning_off_and_temperature_limits():
    assert calls("turn the AC off") == [("set_central_ac", {"target_c": 26.0, "mode": "off"})]
    [(_, hot)] = calls("set it to 40 degrees")
    [(_, cold)] = calls("set the ac to 5")
    assert hot["target_c"] == 30.0 and cold["target_c"] == 16.0


def test_cold_and_hot_move_two_degrees_from_the_current_target():
    get_store("room1").set_reported("central_ac", {"target_c": 24.0, "mode": "cool", "current_c": 24.0})
    assert calls("I'm cold")[0][1]["target_c"] == 26.0
    assert calls("it's hot in here")[0][1]["target_c"] == 22.0


def test_music_keeps_the_volume_when_pausing_and_steps_it():
    get_store("room1").set_reported("bose", {"power": "on", "volume": 40, "playing": True})
    assert calls("pause the music") == [("set_bose", {"power": "on", "volume": 40, "playing": False})]
    assert calls("louder")[0][1]["volume"] == 50
    assert calls("volume down")[0][1]["volume"] == 30
    assert calls("turn the music off")[0][1]["power"] == "off"


def test_the_door_is_not_opened_by_nora():
    p = plan("unlock the door")
    assert p["calls"] == [] and "Unlock" in p["reply"]


def test_bill_and_menu_are_answered_from_the_database():
    assert plan("how much is my bill")["special"] == "bill"
    assert plan("what's on the menu")["special"] == "menu"


# ---------- the full message handler ----------


async def checked_in(session, make_booking):
    booking = await make_booking(room_id="room1")
    await check_in(session, booking)
    return booking


async def test_an_order_is_saved_and_confirmed(session, make_booking):
    booking = await checked_in(session, make_booking)
    out = await handle_message(session, "s", "order 2 coffees", booking_id=booking.id)
    assert "ordering 2 coffees" in out["reply"]
    rows = (await session.execute(select(ServiceOrder))).scalars().all()
    assert [(o.item, o.quantity) for o in rows] == [("coffee", 2)]


async def test_an_order_without_a_stay_is_refused_honestly(session):
    out = await handle_message(session, "s", "order a coffee", booking_id=None)
    assert out["reply"].startswith("Sorry")
    assert "ordering" not in out["reply"]
    assert out["actions"] == []
    assert (await session.execute(select(ServiceOrder))).scalars().all() == []


async def test_the_bill_lists_room_service(session, make_booking):
    booking = await checked_in(session, make_booking)
    await handle_message(session, "s", "order 2 coffees", booking_id=booking.id)
    out = await handle_message(session, "s", "what's my bill", booking_id=booking.id)
    assert "2x coffee" in out["reply"] and "9.00" in out["reply"]  # 2 x 4.50


async def test_the_bill_includes_the_stored_room_price(session, make_booking):
    booking = await checked_in(session, make_booking)
    booking.total_cents = 21600
    booking.currency = "EUR"
    await session.commit()
    out = await handle_message(session, "s", "my bill please", booking_id=booking.id)
    assert "Room: 216.00 EUR" in out["reply"]


async def test_the_menu_lists_prices(session, make_booking):
    booking = await checked_in(session, make_booking)
    out = await handle_message(session, "s", "what's on the menu", booking_id=booking.id)
    assert "coffee 4.50" in out["reply"] and "sandwich 12.00" in out["reply"]


async def test_checkout_time_uses_the_departure_date(session, make_booking, monkeypatch):
    monkeypatch.setenv("CHECKOUT_HOUR", "11")
    booking = await checked_in(session, make_booking)
    booking.planned_check_out = datetime(2026, 12, 29)
    await session.commit()
    out = await handle_message(session, "s", "what time is checkout", booking_id=booking.id)
    assert "Tue 29 Dec" in out["reply"] and "11:00" in out["reply"]


async def test_checking_out_through_nora_ends_the_stay(session, make_booking):
    booking = await checked_in(session, make_booking)
    asked = await handle_message(session, "s", "check me out", booking_id=booking.id)
    assert asked["actions"] == []
    await session.refresh(booking)
    assert booking.status == "CHECKED_IN"

    done = await handle_message(session, "s", "yes, check me out", booking_id=booking.id)
    assert [a["tool"] for a in done["actions"]] == ["checkout"]
    assert done["booking_id"] == booking.id  # the app opens the receipt with this
    await session.refresh(booking)
    assert booking.status == "CHECKED_OUT"


async def test_special_answers_need_a_stay(session):
    out = await handle_message(session, "s", "what's my bill", booking_id=None)
    assert "active stay" in out["reply"]
