"""Bean-029 tests: the reserved-seat flag is a real bool, and so is eligibility.

ac1 — a seat_reserved that is not a bool is refused at construction; True and
     False construct fine, and omitting the field leaves it False.
ac2 — Guest.eligible is the literal True or False by identity for every
      RsvpStatus, including after seat_reserved is reassigned to a non-bool
      on a live guest (dataclasses do not validate on assignment).
"""

import pytest

from seating_planner.domain import Guest, RsvpStatus


def make_guest(status: RsvpStatus, seat_reserved: object = False) -> Guest:
    """Build a guest, allowing non-bool flags so the refusal itself is
    exercised (a valid value never reaches the type check)."""
    return Guest(
        id="g1",
        name="Ada",
        rsvp_status=status,
        seat_reserved=seat_reserved,  # type: ignore[arg-type]
    )


def test_reserved_seat_must_be_a_bool() -> None:
    """ac1: construction accepts only a real bool for seat_reserved."""
    for bad in ("no", "false", "yes", "Yes", "true", 1, 0, None):
        with pytest.raises(ValueError, match="seat_reserved"):
            make_guest(RsvpStatus.PENDING, seat_reserved=bad)
    # The confirmed path must refuse just as hard.
    with pytest.raises(ValueError, match="seat_reserved"):
        make_guest(RsvpStatus.CONFIRMED, seat_reserved="no")
    # A real bool constructs, and is stored untouched.
    assert make_guest(RsvpStatus.PENDING, seat_reserved=True).seat_reserved is True
    assert make_guest(RsvpStatus.PENDING, seat_reserved=False).seat_reserved is False
    # Omitting the field leaves the default.
    assert (
        Guest(id="g2", name="Bea", rsvp_status=RsvpStatus.PENDING).seat_reserved
        is False
    )


def test_eligible_is_always_a_bool() -> None:
    """ac2: eligible is the literal True or False, never the stored value."""
    for status in (
        RsvpStatus.CONFIRMED,
        RsvpStatus.PENDING,
        RsvpStatus.DECLINED,
        RsvpStatus.CANCELLED,
    ):
        for seat_reserved in (True, False):
            guest = make_guest(status, seat_reserved=seat_reserved)
            if status is RsvpStatus.CONFIRMED:
                assert guest.eligible is True
            elif status is RsvpStatus.PENDING:
                assert guest.eligible is (seat_reserved is True)
            else:
                assert guest.eligible is False
    # A pending guest whose flag is reassigned after construction must
    # never report a truthy non-bool as eligibility.
    guest = make_guest(RsvpStatus.PENDING, seat_reserved=True)
    assert guest.eligible is True
    guest.seat_reserved = "no"  # type: ignore[assignment]
    assert guest.eligible is False
    guest.seat_reserved = 1  # type: ignore[assignment]
    assert guest.eligible is False
