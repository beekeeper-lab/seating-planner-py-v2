# bean-029 — A reserved seat is a yes or a no, and every distance measure a rule carries is a real one

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Claude Opus 5.5, under the owner's standing authorisation of 2026-09-29 to act on its recommendations |
| Run order | 29 |
| Depends on | bean-002, bean-003 |
| Size budget | 3 tasks · 5 files · 400 diff lines |

## Intent

A guest's reserved_seat is a bool and eligibility is always a bool derived from it, so a pending guest is seated only with a reserved seat of True; and a minimum-distance rule refuses any measure it is given that is not valid on its own, even beside a valid one.

## Background

Two defects found by the retroactive review of bean-002 and bean-003, both in the checks made when an object is built. The first half of the review's bean-029 finding; the validation of a whole event on use is bean-030.
First: Guest takes reserved_seat without checking its type, and Guest.eligible returns `status is PENDING and self.reserved_seat`, which is the stored value itself. Measured on the main branch: a pending guest built with reserved_seat="no" has eligible == 'no', which is truthy, and a planning solve seats them. The same holds for "false", which is what a CSV column says.
Second: a minimum-distance rule is accepted when distance_m is valid OR min_zones is valid, so a valid measure carries an invalid other into storage. Measured: Rule(..., distance_m="far apart", min_zones=1) is built and stores "far apart", the very phrase FR-035 says shall not be stored as an executable rule.
A caller that reads a reserved seat or a measure from text converts it before building the object; the object does not guess.

## May write

- `src/seating_planner/domain/**`
- `src/seating_planner/rules/**`
- `tests/domain/**`
- `tests/rules/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Building a Guest with a reserved_seat that is not a bool (for example "no", "false", 1 or None) raises a ValueError; True and False are accepted, and the default is still False. | `test` `tests/domain/test_guest_fields.py::test_reserved_seat_must_be_a_bool` |
| ac2 | Guest.eligible is always a bool, True only for a Confirmed guest or a Pending guest whose reserved_seat is True, including when reserved_seat was set to something else after construction. | `test` `tests/domain/test_guest_fields.py::test_eligible_is_always_a_bool` |
| ac3 | A minimum-distance rule, soft or hard, built directly or through from_dict, is refused with a ValueError when a distance_m it is given is not a number greater than zero or a min_zones it is given is not an integer of at least one, whether or not the other measure is valid; a rule with only valid measures is built as before. | `test` `tests/rules/test_distance_measures.py::test_every_given_measure_is_valid` |
| ac4 | Every existing test still passes unchanged. | `command` `pytest -q` |

## Constraints

- a bool is not a number and not an integer here, as everywhere else in the rule model
- an integer distance_m is still accepted and stored as a float
- no solver, store or feasibility code changes

## Non-goals

- no validation of an event on use: solve_event and save_event re-checking what construction checked is bean-030
- no change to how a reserved seat is persisted or loaded
- no change to table capacity or position checks

