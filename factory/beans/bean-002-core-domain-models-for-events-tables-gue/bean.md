# bean-002 — Core domain models for events, tables, guests and groups

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 2 |
| Depends on | bean-001 |
| Size budget | 6 tasks · 5 files · 400 diff lines |

## Intent

The vocabulary of the product exists as validated data structures, so that rules and the solver have something concrete to refer to.

## Background

Everything downstream depends on these shapes. An Event holds Tables and Guests; a Table has a capacity, a shape and an (x, y) position; a Guest has an RSVP status and belongs to a household. Table positions are relative canvas coordinates on an arbitrary unit plane, not physical measurements (see the bean set's recorded assumption for PRD §18.2) — proximity in FR-014 is well defined either way. "Eligible" is a derived property, not a stored field: a guest is eligible when Confirmed, or Pending with an explicitly reserved seat (FR-019).

## May write

- `src/seating_planner/domain/**`
- `tests/domain/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | A Table rejects a capacity below one and rejects a duplicate identifier within an event. | `test` `tests/domain/test_table.py::test_capacity_and_id_validation` |
| ac2 | RSVP status accepts exactly Confirmed, Pending, Declined and Cancelled, and rejects anything else. | `test` `tests/domain/test_guest.py::test_rsvp_status_values` |
| ac3 | A guest is eligible when Confirmed, or Pending with a reserved seat, and not otherwise. | `test` `tests/domain/test_guest.py::test_eligibility_rule` |
| ac4 | A guest may belong to more than one group. | `test` `tests/domain/test_group.py::test_guest_in_multiple_groups` |
| ac5 | An event rejects more than 500 guests, 60 tables, or 5000 rules. | `test` `tests/domain/test_event.py::test_production_limits` |

## Constraints

- no persistence in this bean  
  *checked, not judged:* import `sqlite3`, import `sqlalchemy`, import `psycopg`, import `psycopg2`, import `pymongo`, import `redis`, import `shelve`, import `pickle`
- no solver imports  
  *checked, not judged:* import `ortools`
- table position is a float pair on an arbitrary unit plane

## Non-goals

- no seat-level positions (deferred; see PRD §18.3 assumption)
- no rule model (bean-003)  
  *checked, not judged:* `src/seating_planner/domain/rule*.py`, `src/seating_planner/domain/rules/**`, `src/seating_planner/rules/**`
- no database  
  *checked, not judged:* import `sqlite3`, import `sqlalchemy`, import `psycopg`, import `psycopg2`, import `pymongo`, import `redis`, import `shelve`

