# bean-022 — A group's size in the pre-flight check counts only guests who will be seated

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (owner, directly) |
| Run order | 22 |
| Depends on | bean-005 |
| Size budget | 3 tasks · 3 files · 300 diff lines |

## Intent

The oversized-group pre-flight finding compares a table's capacity with the number of the group's members who are eligible to be seated, so declined and unreserved pending guests do not make a feasible event look impossible.

## Background

A defect found on 2026-09-28 in the code bean-005 shipped. The oversized-group check counts every distinct member id of a group that a hard same-table rule keeps together, including guests who will never be seated: declined guests, and pending guests with no reserved seat. The solver seats only eligible guests (Guest.eligible), so the check reports events the solver could solve.
Measured on the main branch: a family group of 10 with 6 confirmed and 4 declined, one table of 8, and a hard same-table rule on the group is reported as "must stay together at 10, but the largest table seats 8". Six seats are needed. bean-005's own ac2 test builds its group from ten pending guests, none of them eligible, so the test asserts the false positive.
The capacity check in the same module already counts only eligible guests; this bean makes the group check agree with it.

## May write

- `src/seating_planner/feasibility/**`
- `tests/feasibility/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A group kept together by a hard same-table rule whose eligible members fit the largest table produces no oversized-group finding, however many ineligible members it has. | `test` `tests/feasibility/test_group_eligibility.py::test_ineligible_members_do_not_count` |
| ac2 | A group whose eligible members exceed the largest table is still reported, and the reported size is the number of eligible members. | `test` `tests/feasibility/test_group_eligibility.py::test_eligible_members_are_the_size` |
| ac3 | Every pre-flight test passes, with the group test's fixture made of guests who would be seated. | `command` `pytest -q tests/feasibility` |

## Constraints

- eligibility comes from Guest.eligible, never from a status list copied here
- no solver imports, as in bean-005

## Non-goals

- no change to the contradiction, capacity or missing-target checks

