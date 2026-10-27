# bean-025 — Event-day unlock releases explicit locks, and a missing seat is not blamed on unrelated rules

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly) |
| Run order | 25 |
| Depends on | bean-014 |
| Size budget | 3 tasks · 3 files · 450 diff lines |

## Intent

In event-day mode an explicitly unlocked guest may move even when an explicit lock also names them, and an event-day solve that cannot seat a new guest reports only the hard rules whose removal alone would let it solve with the chart still in place.

## Background

Two defects found by bean-014's pre-merge review, merged on the owner's decision with this bean as the repair.
First: the event-day solve skips its own day-lock pin for a guest in `unlocked`, but the model it builds still applies every entry in `event.locks`, so a guest who is both explicitly locked and explicitly unlocked cannot move, and nothing says so. Measured on the main branch: g-2 locked to t-2 and unlocked, with a weight-100 reason to join t-1, stays at t-2. bean-014's ac4 test uses no explicit locks.
Second: when a new guest cannot be seated, the event-day solve hands its infeasibility to the ordinary one-removal diagnosis, whose probe models do not carry the day-lock pins. Without the pins, removing almost any hard rule leaves something solvable, so unrelated rules are named, and a recommendation to relax one is given that would not help. Measured: a hard different-table rule already satisfied by the chart was named beside the rule that actually explains the missing seat. "No seat for the new guest" is the most common way this mode fails.
Run 1 (bean-025-20261006T140110Z, PR #22) fixed both, and its pre-merge review found that the event-day diagnosis it wrote no longer checks locks at all. Its spec assumed that "removing a stored lock can never be what restores feasibility" in event-day. That is false: a new guest locked to a table the chart already fills, or a chart guest whose lock names a different table from the chart and who is not unlocked, makes the solve infeasible because of the lock alone. On main the report says to unlock that guest; run 1's report said only "The enabled hard rules are jointly unsatisfiable", in an event with no hard rule (evidence/reviews/bean-025-20261006T140110Z.md).

## May write

- `src/seating_planner/solver/**`
- `tests/solver/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | In event-day mode, a guest who is explicitly locked and also named in unlocked may be moved to another table when that raises the soft score, and nobody else moves. | `test` `tests/solver/test_event_day_repairs.py::test_unlock_releases_an_explicit_lock` |
| ac2 | An event-day solve that cannot seat a new guest names only hard rules whose removal alone makes it solvable with every chart guest in place, and recommends capacity when no rule removal would help. | `test` `tests/solver/test_event_day_repairs.py::test_no_seat_blames_only_rules_that_explain_it` |
| ac4 | In event-day mode, when a stored lock is what makes the solve infeasible (a new guest locked to a table the chart fills, or a chart guest locked to a table other than the one the chart gives them and not in unlocked), the report recommends unlocking that guest, and when the event has no hard rule it does not recommend reviewing hard rules. | `test` `tests/solver/test_event_day_repairs.py::test_a_lock_that_causes_no_seat_is_named` |
| ac3 | Every existing solver test still passes unchanged. | `command` `pytest -q tests/solver` |

## Constraints

- an explicit lock without an unlock still holds in every mode
- the solve_event signature and the result shape are unchanged

## Non-goals

- no change to the planning or low-disruption diagnosis
- no mode comparison changes (bean-023)

