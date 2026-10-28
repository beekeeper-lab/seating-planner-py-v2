"""Task-1 tests: the RSVP vocabulary and the derived eligibility rule."""

import pytest

from seating_planner.domain import Guest, RsvpStatus


def make_guest(status: RsvpStatus, seat_reserved: bool = False) -> Guest:
    return Guest(
        id="g1",
        name="Ada",
        rsvp_status=status,
        household=None,
        seat_reserved=seat_reserved,
    )


def test_rsvp_status_values() -> None:
    """The four accepted words each give the right member; others raise."""
    assert RsvpStatus("Confirmed") is RsvpStatus.CONFIRMED
    assert RsvpStatus("Pending") is RsvpStatus.PENDING
    assert RsvpStatus("Declined") is RsvpStatus.DECLINED
    assert RsvpStatus("Cancelled") is RsvpStatus.CANCELLED
    for value in (
        RsvpStatus.CONFIRMED,
        RsvpStatus.PENDING,
        RsvpStatus.DECLINED,
        RsvpStatus.CANCELLED,
    ):
        assert value.value in {"Confirmed", "Pending", "Declined", "Cancelled"}
    with pytest.raises(ValueError):
        RsvpStatus("confirmed")
    with pytest.raises(ValueError):
        RsvpStatus("Attending")


def test_guest_coerces_and_validates_a_raw_rsvp_string() -> None:
    """ac2/ac3 apply to Guest construction, not just RsvpStatus itself: a raw
    string is normalised to the enum, and an invalid one is rejected the same
    way an invalid RsvpStatus value is."""
    g = Guest(id="g1", name="Ada", rsvp_status="Confirmed")
    assert g.rsvp_status is RsvpStatus.CONFIRMED
    assert g.eligible
    with pytest.raises(ValueError):
        Guest(id="g2", name="Bea", rsvp_status="Attending")


def test_eligibility_rule() -> None:
    """Eligible when Confirmed, or Pending with a reserved seat, not otherwise."""
    assert make_guest(RsvpStatus.CONFIRMED).eligible
    assert make_guest(RsvpStatus.CONFIRMED, seat_reserved=True).eligible
    assert make_guest(RsvpStatus.CONFIRMED, seat_reserved=False).eligible
    assert make_guest(RsvpStatus.PENDING, seat_reserved=True).eligible
    assert not make_guest(RsvpStatus.PENDING, seat_reserved=False).eligible
    assert not make_guest(RsvpStatus.DECLINED, seat_reserved=True).eligible
    assert not make_guest(RsvpStatus.CANCELLED, seat_reserved=True).eligible
