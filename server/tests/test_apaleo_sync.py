from datetime import datetime
from types import SimpleNamespace

from server.apaleo_sync import reconcile
from server.booking_service import CANCELED, CHECKED_IN, NO_SHOW, RESERVED, CHECKED_OUT


def make(status=RESERVED):
    return SimpleNamespace(
        status=status,
        planned_check_in=datetime(2026, 12, 10),
        planned_check_out=datetime(2026, 12, 12),
        actual_check_out = None,
    )


def test_cancel_marks_reserved_booking_canceled():
    booking = make()
    changes = reconcile(booking, {"status": "Canceled"})
    assert booking.status == CANCELED
    assert changes


def test_no_show():
    booking = make()
    reconcile(booking, {"status": "NoShow"})
    assert booking.status == NO_SHOW


def test_cancel_never_overrides_a_guest_who_is_in_the_room():
    booking = make(CHECKED_IN)
    changes = reconcile(booking, {"status": "Canceled"})
    assert booking.status == CHECKED_IN
    assert changes == []


def test_date_change_is_applied():
    booking = make()
    reservation = {
        "status": "Confirmed",
        "arrival": "2026-12-11T15:00:00+01:00",
        "departure": "2026-12-14T11:00:00+01:00",
    }
    assert len(reconcile(booking, reservation)) == 2
    assert booking.planned_check_in == datetime(2026, 12, 11)
    assert booking.planned_check_out == datetime(2026, 12, 14)


def test_same_dates_means_no_changes():
    booking = make()
    reservation = {
        "status": "Confirmed",
        "arrival": "2026-12-10T15:00:00+01:00",
        "departure": "2026-12-12T11:00:00+01:00",
    }
    assert reconcile(booking, reservation) == []


def test_garbage_is_ignored():
    booking = make()
    assert reconcile(booking, {"arrival": 5, "departure": "x", "status": None}) == []

def test_checkout_in_apaleo_closes_a_booking_that_was_in_the_room():
    booking = make(CHECKED_IN)
    changes = reconcile(booking, {"status": "CheckedOut"})
    assert booking.status == CHECKED_OUT
    assert booking.actual_check_out is not None
    assert "room needs reset" in changes


def test_checkout_of_a_booking_never_checked_in_needs_no_room_reset():
    booking = make(RESERVED)
    changes = reconcile(booking, {"status": "CheckedOut"})
    assert booking.status == CHECKED_OUT
    assert "room needs reset" not in changes


def test_checkout_seen_twice_changes_nothing():
    booking = make(CHECKED_OUT)
    booking.actual_check_out = datetime(2026, 12, 12)
    assert reconcile(booking, {"status": "CheckedOut"}) == [] 