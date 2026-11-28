from datetime import datetime

from server import door_access, ttlock
from server.apaleo_sync import process_event
from server.booking_service import CANCELED, CHECKED_IN, CHECKED_OUT, check_in
from server.models import RoomStatus
from server.rooms import assign_room


class FakeApaleo:
    def __init__(self, reservation):
        self.reservation = reservation

    async def get(self, path):
        return self.reservation


def event(reservation_id="RES-1"):
    return {"topic": "reservation", "data": {"entityId": reservation_id}}


async def linked(session, make_booking, room="room1", arrive=datetime(2030, 1, 10), leave=datetime(2030, 1, 12)):
    booking = await make_booking(room_id=room)
    booking.apaleo_reservation_id = "RES-1"
    booking.planned_check_in = arrive
    booking.planned_check_out = leave
    await session.commit()
    return booking


async def test_a_check_out_in_apaleo_removes_the_door_code_and_marks_the_room_dirty(session, make_booking):
    booking = await linked(session, make_booking)
    await check_in(session, booking)
    assert booking.door_pin is not None

    outcome = await process_event(session, FakeApaleo({"status": "CheckedOut"}), event())
    await session.commit()

    assert booking.status == CHECKED_OUT
    assert booking.door_pin is None and booking.door_pin_id is None and booking.door_pin_expires is None
    assert "door code removed" in outcome
    assert ttlock.get_ttlock().passcodes == {}  # gone from the lock too
    status = await session.get(RoomStatus, "room1")
    assert status.clean_state == "dirty"


async def test_an_extension_keeps_the_same_code_with_a_later_end(session, make_booking):
    booking = await linked(session, make_booking)
    await check_in(session, booking)
    pin, old_end = booking.door_pin, booking.door_pin_expires

    reservation = {"status": "InHouse", "departure": "2030-01-14T11:00:00+01:00"}
    outcome = await process_event(session, FakeApaleo(reservation), event())

    assert booking.status == CHECKED_IN
    assert booking.planned_check_out == datetime(2030, 1, 14)
    assert booking.door_pin == pin
    assert booking.door_pin_expires > old_end
    assert "door code renewed" in outcome
    [on_lock] = ttlock.get_ttlock().passcodes.values()  # exactly one code, with the new end
    assert on_lock["pin"] == pin and on_lock["end"] == booking.door_pin_expires


async def test_a_shorter_stay_ends_the_code_earlier(session, make_booking):
    booking = await linked(session, make_booking, leave=datetime(2030, 1, 15))
    await check_in(session, booking)
    old_end = booking.door_pin_expires

    await process_event(
        session, FakeApaleo({"status": "InHouse", "departure": "2030-01-12T11:00:00+01:00"}), event()
    )
    assert booking.door_pin_expires < old_end


async def test_unchanged_dates_leave_the_code_alone(session, make_booking):
    booking = await linked(session, make_booking)
    await check_in(session, booking)
    before = (booking.door_pin, booking.door_pin_id, booking.door_pin_expires)

    outcome = await process_event(
        session, FakeApaleo({"status": "InHouse", "departure": "2030-01-12T11:00:00+01:00"}), event()
    )
    assert (booking.door_pin, booking.door_pin_id, booking.door_pin_expires) == before
    assert "no changes" in outcome


async def test_a_cancellation_in_apaleo_frees_the_room(session, make_booking):
    booking = await linked(session, make_booking)
    arrival, departure = datetime(2030, 1, 10), datetime(2030, 1, 12)
    assert await assign_room(session, arrival, departure) == "room2"  # room1 is taken

    await process_event(session, FakeApaleo({"status": "Canceled"}), event())
    await session.commit()

    assert booking.status == CANCELED
    assert await assign_room(session, arrival, departure) == "room1"


async def test_a_failed_renewal_is_reported_not_raised(session, make_booking, monkeypatch):
    booking = await linked(session, make_booking)
    await check_in(session, booking)
    monkeypatch.setattr(door_access, "lock_id_for", lambda room: None)

    result = await door_access.refresh_door_pin(booking)
    assert result["door_pin_issued"] is False
    assert "No lock" in result["door_pin_error"]
    assert booking.door_pin is not None  # the old code is untouched


async def test_a_booking_without_a_code_gets_one_when_refreshed(session, make_booking):
    booking = await linked(session, make_booking)
    booking.status = CHECKED_IN
    result = await door_access.refresh_door_pin(booking)
    assert result["door_pin_issued"] is True
    assert booking.door_pin
