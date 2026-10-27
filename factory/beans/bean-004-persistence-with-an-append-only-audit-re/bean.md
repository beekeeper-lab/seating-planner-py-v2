# bean-004 — Persistence with an append-only audit record

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 4 |
| Depends on | bean-003 |
| Size budget | 6 tasks · 5 files · 600 diff lines |

## Intent

Events, guests, rules and assignments survive a process restart, and every change to them is attributable to a user and a time.

## Background

A repository (in the storage sense) is the seam between domain objects and where they are stored: the rest of the code asks it to load and save, and does not know whether the answer came from memory or SQLite. NFR-013 is the demanding part — a write that fails partway must leave the previous state intact rather than a half-updated chart, which means each save is one transaction. Concurrent editing is last-write-wins for v1 (see the recorded assumption for PRD §18.1); the audit record is what makes that reconstructable afterward.

## May write

- `src/seating_planner/store/**`
- `tests/store/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | An event with guests, tables and rules saves and loads back equal to what was saved. | `test` `tests/store/test_repository.py::test_event_roundtrip` |
| ac2 | Every mutation writes an audit entry carrying actor, timestamp, entity type and entity id. | `test` `tests/store/test_audit.py::test_mutation_writes_audit_entry` |
| ac3 | A write that raises partway leaves the previously committed state readable and unchanged. | `test` `tests/store/test_repository.py::test_failed_write_is_atomic` |
| ac4 | The audit log is append-only — an attempt to modify or delete an existing entry is rejected. | `test` `tests/store/test_audit.py::test_audit_log_is_append_only` |
| ac5 | Removing a guest, table, group or rule from a saved event and saving again writes an audit entry for the removed entity, carrying actor, timestamp, entity type and entity id. | `test` `tests/store/test_audit.py::test_removal_writes_audit_entry` |

## Constraints

- SQLite only; no external database service  
  *checked, not judged:* import `psycopg`, import `psycopg2`, import `pymysql`, import `MySQLdb`, import `pymongo`, import `redis`
- no ORM dependency beyond the standard library  
  *checked, not judged:* import `sqlalchemy`, import `peewee`, import `tortoise`, import `pony`, import `django`

## Non-goals

- no migrations framework  
  *checked, not judged:* import `alembic`, import `yoyo`
- no multi-user conflict resolution (last write wins; see PRD §18.1 assumption)
- no encryption at rest (deployment concern, excluded from the corpus)  
  *checked, not judged:* import `cryptography`, import `nacl`, import `pysqlcipher3`

