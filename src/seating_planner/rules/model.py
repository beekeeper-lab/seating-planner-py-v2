"""The rule model: kinds, hardness, soft weights and serialization.

A rule is explicit, structured data — never prose. Construction validates the
shape of each rule so that a soft rule without a usable weight, a hard rule
with one, or a min-distance rule with no numeric measure (FR-035: "far apart"
is not a measurement) is rejected at the point it is written down. Evaluation
of rules belongs to a later bean; this module only defines and checks data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeGuard

#: Inclusive lower bound of a soft rule's integer weight.
MIN_WEIGHT: int = 1
#: Inclusive upper bound of a soft rule's integer weight.
MAX_WEIGHT: int = 100


class RuleKind(str, Enum):
    """What a rule says: sit together, sit apart, stay distant, sit next to."""

    SAME_TABLE = "same_table"
    DIFFERENT_TABLE = "different_table"
    MIN_DISTANCE = "min_distance"
    ADJACENT_SEAT = "adjacent_seat"


class Hardness(str, Enum):
    """Whether a rule may be broken: never (hard) or with cost (soft)."""

    HARD = "hard"
    SOFT = "soft"


def _is_real_int(value: object) -> TypeGuard[int]:
    """True for an int that is not a bool (bool is a subclass of int)."""
    return type(value) is int


def _is_positive_number(value: object) -> bool:
    """True for a number strictly above zero, where a bool is not a number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


@dataclass
class Rule:
    """A single structured seating rule, covering every kind in one shape.

    The rule binds to at least two guest ids or to one group; only
    min_distance rules may carry ``target``, ``distance_m`` or ``min_zones``.
    Soft rules carry an integer weight in 1..100; hard rules carry none.
    """

    id: str
    kind: RuleKind
    hardness: Hardness
    guests: tuple[str, ...] = ()
    group_id: str | None = None
    weight: int | None = None
    enabled: bool = True
    target: str | None = None
    distance_m: float | None = None
    min_zones: int | None = None

    def __post_init__(self) -> None:
        self.kind = RuleKind(self.kind)
        self.hardness = Hardness(self.hardness)
        self.guests = tuple(self.guests)

        if not isinstance(self.id, str) or not self.id:
            raise ValueError(f"a rule id must be a non-empty string, got {self.id!r}")
        if not isinstance(self.enabled, bool):
            raise TypeError(
                f"a rule's enabled flag must be a bool, got {self.enabled!r}"
            )

        if self.hardness is Hardness.SOFT:
            if (
                not _is_real_int(self.weight)
                or not MIN_WEIGHT <= self.weight <= MAX_WEIGHT
            ):
                raise ValueError(
                    f"a soft rule requires an integer weight in "
                    f"{MIN_WEIGHT}..{MAX_WEIGHT}, got {self.weight!r}"
                )
        elif self.weight is not None:
            raise ValueError(f"a hard rule carries no weight, got {self.weight!r}")

        if self.kind is RuleKind.MIN_DISTANCE:
            distance_ok = _is_positive_number(self.distance_m)
            zones_ok = _is_real_int(self.min_zones) and self.min_zones >= 1
            if not distance_ok and not zones_ok:
                raise ValueError(
                    "a min_distance rule needs a numeric distance_m above zero or a "
                    f"zone count of at least one; got distance_m={self.distance_m!r} "
                    f"and min_zones={self.min_zones!r} (FR-035)"
                )
        else:
            if (
                self.target is not None
                or self.distance_m is not None
                or self.min_zones is not None
            ):
                raise ValueError(
                    f"only min_distance rules may carry target/distance_m/min_zones, "
                    f"got target={self.target!r} distance_m={self.distance_m!r} "
                    f"min_zones={self.min_zones!r}"
                )
            if len(self.guests) < 2 and self.group_id is None:
                raise ValueError(
                    "a rule must bind to at least two guest ids or to a group, "
                    f"got guests={self.guests!r} and group_id={self.group_id!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Flat, JSON-serialisable mapping of all ten fields."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "hardness": self.hardness.value,
            "guests": list(self.guests),
            "group_id": self.group_id,
            "weight": self.weight,
            "enabled": self.enabled,
            "target": self.target,
            "distance_m": self.distance_m,
            "min_zones": self.min_zones,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        """Rebuild a rule from a mapping, requiring only id, kind and hardness.

        Everything else defaults to the constructor defaults, and the rebuild
        goes through the constructor so every load is validated again.
        """
        missing = [key for key in ("id", "kind", "hardness") if key not in data]
        if missing:
            raise ValueError(
                f"a rule mapping is missing required field(s): {missing!r}"
            )
        return cls(
            id=data["id"],
            kind=RuleKind(data["kind"]),
            hardness=Hardness(data["hardness"]),
            guests=tuple(data.get("guests", ())),
            group_id=data.get("group_id"),
            weight=data.get("weight"),
            enabled=data.get("enabled", True),
            target=data.get("target"),
            distance_m=data.get("distance_m"),
            min_zones=data.get("min_zones"),
        )
