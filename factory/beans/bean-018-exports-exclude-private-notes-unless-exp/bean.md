# bean-018 — Exports exclude private notes unless explicitly and visibly included

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 18 |
| Depends on | bean-016 |
| Size budget | 6 tasks · 5 files · 600 diff lines |

## Intent

A guest-to-table export carries no private notes, relationship rules or override explanations, and including them requires a deliberate choice that names what will be exposed.

## Background

Private notes are where an organizer records that two guests are not speaking. A leak here is the worst failure this product can have, and it happens by omission — someone adds a field to a guest record and the export picks it up automatically. The defence is to build exports from an explicit allow-list of fields rather than by serializing the guest object, so a new private field is excluded by default rather than included by default. AC-008 in the PRD is the scenario this must satisfy.
Run 1 built the allow-list, warning and audit entry correctly but ordered the write wrong: the export's write() put the CSV on disk and only then opened the audit log to append the record. When the audit path cannot be opened (missing directory, a directory where the file should be, read-only, full disk) it raised after the private CSV already existed -- private data on disk with no audit record, the exact case the audit exists to catch. Measured: write(csv_path, "<tmp>/no-such-dir/audit.jsonl") on a private export raised FileNotFoundError and left the CSV behind.
Ready-made fixture for ac6's own test: a private export (include_private naming a private field) written with an audit path whose parent directory does not exist. A correct implementation raises and leaves NOTHING at the CSV path -- by appending the audit record first, or by writing the CSV to a temporary file and renaming it into place only after the audit append succeeded. A second case in the same test: a writable audit path still produces both the CSV and exactly one audit line, so the fix cannot simply refuse every private write.

## May write

- `src/seating_planner/export/**`
- `tests/export/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | The default guest-to-table CSV contains no private note, relationship note, rule definition or override explanation. | `test` `tests/export/test_privacy.py::test_default_export_excludes_private_fields` |
| ac2 | Adding a new field to the guest model does not cause it to appear in an export. | `test` `tests/export/test_privacy.py::test_export_uses_allowlist_not_serialization` |
| ac3 | Requesting private fields returns a warning naming each included field before the file is produced. | `test` `tests/export/test_privacy.py::test_private_export_warns_and_names_fields` |
| ac4 | An export containing private data writes an audit entry recording that it did. | `test` `tests/export/test_privacy.py::test_private_export_is_audited` |
| ac5 | The table-by-table CSV export lists every assigned guest exactly once. | `test` `tests/export/test_csv.py::test_table_by_table_export_complete` |
| ac6 | A private export is never left on disk without its audit record -- when the audit record cannot be written, write() raises and no CSV exists at the target path. | `test` `tests/export/test_privacy.py::test_unwritable_audit_path_leaves_no_private_csv` |

## Constraints

- exports are built from an explicit field allow-list
- the audit record is written before, or atomically with, the private CSV becoming visible at its target path
- CSV only in this bean  
  *checked, not judged:* import `openpyxl`, import `xlsxwriter`, import `xlwt`

## Non-goals

- no PDF rendering (excluded from the corpus; see manifest scope_exclusions)  
  *checked, not judged:* import `reportlab`, import `fpdf`, import `fpdf2`, import `weasyprint`, import `pypdf`, import `PyPDF2`, import `pdfkit`

