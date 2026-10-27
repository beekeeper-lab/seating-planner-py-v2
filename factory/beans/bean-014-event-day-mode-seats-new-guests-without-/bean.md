# bean-014 — Event-day mode seats new guests without moving anyone

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 14 |
| Depends on | bean-013 |
| Size budget | 6 tasks · 4 files · 550 diff lines |

## Intent

On the day, every existing assignment is treated as locked, a newly added guest takes an open seat, and a cancellation frees a seat without shuffling anyone.

## Background

Guests are seated and the room is full of people; moving someone now means walking up to them mid-reception. So the mode inverts the default: everything already assigned is locked whether or not the organizer locked it explicitly, and only the new guest is a free variable. The trap is the cancellation case — freeing a seat creates an opportunity to improve the chart, and the system must decline to take it. An automatic improvement here is a defect, not a feature.

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | Adding a guest with an open seat available assigns them and moves nobody else. | `test` `tests/solver/test_event_day.py::test_new_guest_takes_open_seat` |
| ac2 | Existing assignments are treated as locked even when no explicit lock was set. | `test` `tests/solver/test_event_day.py::test_existing_assignments_implicitly_locked` |
| ac3 | Cancelling a guest frees their seat and moves no other guest. | `test` `tests/solver/test_event_day.py::test_cancellation_moves_nobody` |
| ac4 | An explicitly unlocked guest may be moved in Event-day mode. | `test` `tests/solver/test_event_day.py::test_explicit_unlock_permits_move` |
| ac5 | A new guest is placed only where every hard constraint holds. | `test` `tests/solver/test_event_day.py::test_new_guest_respects_hard_rules` |

## Constraints

- no opportunistic reoptimization after a cancellation

## Non-goals

- no ranked alternatives when no seat fits (bean-015)

