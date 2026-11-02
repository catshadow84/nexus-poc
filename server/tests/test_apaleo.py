from datetime import date, timedelta

import pytest

from server.apaleo import (
    ApaleoError,
    extract_ids,
    simplify_offer,
    split_name,
    validate_stay,
)

TODAY = date.today()


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def test_validate_stay_accepts_a_normal_stay():
    validate_stay(day(5), day(7), 2)


@pytest.mark.parametrize(
    "arrival, departure, adults, message",
    [
        (-1, 2, 2, "past"),
        (5, 5, 2, "after arrival"),
        (5, 4, 2, "after arrival"),
        (5, 40, 2, "30 nights"),
        (5, 7, 0, "adults"),
        (5, 7, 7, "adults"),
    ],
)
def test_validate_stay_rejects_bad_input(arrival, departure, adults, message):
    with pytest.raises(ValueError, match=message):
        validate_stay(day(arrival), day(departure), adults)


def test_split_name():
    assert split_name("Sarah Khoury") == ("Sarah", "Khoury")
    assert split_name("Mary Jane Watson") == ("Mary", "Jane Watson")
    assert split_name("Madonna") == ("Madonna", "Madonna")


OFFER = {
    "ratePlan": {"id": "BER-FLEX", "name": "Flexible"},
    "unitGroup": {"name": "Double"},
    "minGuaranteeType": "CreditCard",
    "availableUnits": 49,
    "totalGrossAmount": {"amount": 234.0, "currency": "EUR"},
}


def test_simplify_offer():
    assert simplify_offer(OFFER) == {
        "rate_plan_id": "BER-FLEX",
        "room_type": "Double",
        "rate_plan": "Flexible",
        "total_amount": 234.0,
        "currency": "EUR",
        "guarantee": "CreditCard",
        "available_units": 49,
        "bookable": True,
    }


def test_prepayment_offers_are_not_bookable():
    assert simplify_offer({**OFFER, "minGuaranteeType": "Prepayment"})["bookable"] is False


def test_extract_ids():
    response = {"id": "ABCDEFGH", "reservationIds": [{"id": "ABCDEFGH-1"}]}
    assert extract_ids(response) == ("ABCDEFGH", "ABCDEFGH-1")


def test_extract_ids_refuses_an_unexpected_response():
    with pytest.raises(ApaleoError):
        extract_ids({"something": "else"})