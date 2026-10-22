import pytest

from server.booking_service import (
    CHECKED_IN,
    CHECKED_OUT,
    RESERVED,
    check_in,
    check_out,
)

FULL_PREFS = {
    "light": {"power": "on", "brightness": 60, "color": "warm"},
    "thermostat": {"target_c": 21, "mode": "cool"},
    "curtain": {"open_pct": 30},
}


def commands_by_topic(published):
    return {topic: payload["value"] for topic, payload in published}


async def test_check_in_marks_booking_checked_in(session, make_booking):
    booking = await make_booking()
    await check_in(session, booking)
    assert booking.status == CHECKED_IN
    assert booking.actual_check_in is not None


async def test_check_in_applies_guest_preferences(session, make_booking, published):
    booking = await make_booking(preferences=FULL_PREFS)
    result = await check_in(session, booking)
    assert sorted(result["applied_devices"]) == ["curtain", "light", "thermostat"]
    assert commands_by_topic(published) == {
        "nexus/room1/light/command": {"power": "on", "brightness": 60, "color": "warm"},
        "nexus/room1/thermostat/command": {"target_c": 21, "mode": "cool"},
        "nexus/room1/curtain/command": {"open_pct": 30},
    }


async def test_invalid_or_unknown_preferences_are_skipped(session, make_booking, published):
    prefs = {
        "light": {"power": "on", "brightness": 500, "color": "warm"},  # brightness too high
        "toaster": {"power": "on"},  # not a real device
        "curtain": {"open_pct": 30},  # valid
    }
    booking = await make_booking(preferences=prefs)
    result = await check_in(session, booking)
    assert result["applied_devices"] == ["curtain"]
    assert set(commands_by_topic(published)) == {"nexus/room1/curtain/command"}


async def test_cannot_check_in_twice(session, make_booking):
    booking = await make_booking()
    await check_in(session, booking)
    with pytest.raises(ValueError, match="already checked in"):
        await check_in(session, booking)


async def test_second_guest_cannot_take_occupied_room(session, make_booking):
    first = await make_booking(room_id="room1")
    second = await make_booking(room_id="room1")
    await check_in(session, first)
    with pytest.raises(ValueError, match="occupied"):
        await check_in(session, second)
    assert second.status == RESERVED  # failed attempt changed nothing


async def test_different_rooms_can_both_be_occupied(session, make_booking):
    first = await make_booking(room_id="room1")
    second = await make_booking(room_id="room2")
    await check_in(session, first)
    await check_in(session, second)
    assert first.status == CHECKED_IN
    assert second.status == CHECKED_IN


async def test_cannot_check_in_after_check_out(session, make_booking):
    booking = await make_booking()
    await check_in(session, booking)
    await check_out(session, booking)
    with pytest.raises(ValueError, match="completed"):
        await check_in(session, booking)


async def test_check_out_resets_the_room(session, make_booking, published):
    booking = await make_booking(room_id="room2", preferences=FULL_PREFS)
    await check_in(session, booking)
    published.clear()  # forget the check-in commands, we only want the reset

    result = await check_out(session, booking)

    assert result == {"reset": True}
    assert booking.status == CHECKED_OUT
    assert booking.actual_check_out is not None
    assert commands_by_topic(published) == {
        "nexus/room2/light/command": {"power": "off", "brightness": 0, "color": "neutral"},
        "nexus/room2/thermostat/command": {"target_c": 22.0, "mode": "cool"},
        "nexus/room2/curtain/command": {"open_pct": 0},
    }


async def test_cannot_check_out_a_booking_that_is_not_checked_in(session, make_booking):
    booking = await make_booking()
    with pytest.raises(ValueError, match="not checked in"):
        await check_out(session, booking)


async def test_room_is_free_again_after_check_out(session, make_booking):
    first = await make_booking(room_id="room1")
    second = await make_booking(room_id="room1")
    await check_in(session, first)
    await check_out(session, first)
    await check_in(session, second)
    assert second.status == CHECKED_IN