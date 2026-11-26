import pytest

from server import passwords
from server.passwords import (
    check_password_rules,
    hash_password,
    is_locked,
    note_failure,
    reset_throttle,
    verify_password,
)


@pytest.fixture(autouse=True)
def clean_throttle():
    reset_throttle()
    yield
    reset_throttle()


def test_a_password_checks_out_against_its_own_hash():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("correct horse batter", stored)


def test_the_same_password_gets_a_different_hash_each_time():
    assert hash_password("same password 1") != hash_password("same password 1")


def test_the_password_itself_is_not_in_the_hash():
    assert "correct horse" not in hash_password("correct horse battery")


@pytest.mark.parametrize("junk", ["", "plain", "scrypt$1$2", "md5$1$2$3$ab$cd", "scrypt$x$y$z$zz$zz"])
def test_garbage_in_the_database_never_verifies_and_never_crashes(junk):
    assert verify_password("anything at all", junk) is False


def test_short_passwords_are_refused():
    with pytest.raises(ValueError, match="at least 10"):
        check_password_rules("short")
    check_password_rules("long enough pw")


def test_five_wrong_attempts_lock_the_name_and_others_are_unaffected():
    for _ in range(4):
        note_failure("amal")
    assert not is_locked("amal")
    note_failure("amal")
    assert is_locked("amal")
    assert not is_locked("omar")


def test_old_failures_stop_counting(monkeypatch):
    for _ in range(5):
        note_failure("amal")
    assert is_locked("amal")
    later = passwords.time.time() + passwords.WINDOW_SECONDS + 1
    monkeypatch.setattr(passwords.time, "time", lambda: later)
    assert not is_locked("amal")