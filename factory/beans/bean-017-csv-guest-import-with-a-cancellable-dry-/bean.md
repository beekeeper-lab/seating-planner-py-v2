# bean-017 — CSV guest import with a cancellable dry-run preview

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 17 |
| Depends on | bean-004 |
| Size budget | 6 tasks · 5 files · 700 diff lines |

## Intent

A guest list arrives as a spreadsheet, and the organizer sees exactly what the import would do — and can walk away — before any data changes.

## Background

Importing is the highest-volume way to get things wrong, so the preview is the feature and the write is the afterthought. The preview reports four things: rows that cannot be parsed, rows missing something required, rows that look like a guest already present, and the counts that would be created or updated. "Likely duplicate" needs a stated rule rather than a guess — matching on normalized name within the same household is enough, and the preview should say that is what it did. Cancelling must leave the event untouched, which is easiest to guarantee by doing the whole preview without opening a write transaction at all.
Run 1 built a clean preview/apply split but picked up a real defect only apply-time sequencing could expose: a no-id create row is assigned an auto-generated "imported-N" id by scanning the existing guests at the moment that row is applied, but nothing reserves that id against an id a LATER row in the same file carries literally. A file where row 1 has no id (so it is assigned "imported-1") and a later row happens to carry the literal id "imported-1" (matching no existing guest, so the preview classifies it as an ordinary create, not a file-duplicate) passes preview as entirely clean, then crashes apply with an uncaught ValueError from the domain's own id-uniqueness check — the row ordering inside one file decides whether a preview-clean import can even complete. The fix is to reserve every id, up front, before generating any auto id: compute the full set of ids this apply will use — every existing guest id, plus every literal id any row in the file carries — once, before applying any row, and have auto-id generation skip anything in that set, not just what currently happens to be in `event.guests`.
Ready-made fixture for ac6's own test: a two-row CSV, `name,status,id` header, row 1 `Alice,confirmed,` (no id — would be auto-assigned "imported-1" under the old, buggy sequencing), row 2 `Bob,confirmed,imported-1` (an explicit, literal id that matches no existing guest). Against an empty event, preview_import reports `would_create == 2`, `invalid == ()`, `missing == ()`, `duplicates == ()` — a preview-clean file. The old code raises an uncaught ValueError from apply(); the fix applies both rows without error, ending with two guests whose ids are distinct (row 2 keeps its literal "imported-1"; row 1 is auto-assigned a different id, e.g. "imported-2", since "imported-1" is now reserved before any auto-id is chosen).

## May write

- `src/seating_planner/importer/**`
- `tests/importer/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | The preview reports invalid rows, rows with missing required fields, likely duplicates, and create/update counts. | `test` `tests/importer/test_preview.py::test_preview_reports_all_four_categories` |
| ac2 | Generating a preview writes nothing to the event. | `test` `tests/importer/test_preview.py::test_preview_is_read_only` |
| ac3 | Cancelling after a preview leaves the event byte-identical. | `test` `tests/importer/test_preview.py::test_cancel_changes_nothing` |
| ac4 | Applying an import creates and updates exactly the counts the preview reported. | `test` `tests/importer/test_apply.py::test_apply_matches_preview_counts` |
| ac5 | A file with some invalid rows imports the valid ones only when the organizer opts in, never silently. | `test` `tests/importer/test_apply.py::test_partial_import_requires_opt_in` |
| ac6 | A later row's explicit id never collides with an id the import auto-generated for an earlier no-id row — a preview-clean file always applies without error, regardless of row order. | `test` `tests/importer/test_apply.py::test_an_explicit_id_never_collides_with_an_earlier_auto_generated_one` |

## Constraints

- duplicate detection uses a stated, testable rule
- preview opens no write transaction
- auto-generated ids are reserved against every id the whole file will use, computed before any row is applied, not just the ids already present on the event at that moment

## Non-goals

- no Excel or Google Sheets formats  
  *checked, not judged:* import `openpyxl`, import `xlrd`, import `xlwt`, import `xlsxwriter`, import `pyexcel`, import `gspread`, import `googleapiclient`
- no column auto-mapping UI

