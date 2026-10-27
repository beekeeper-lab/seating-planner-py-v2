# bean-001 — Project scaffold with linting, typing and test gates

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 1 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 1 |
| Depends on | nothing |
| Size budget | 4 tasks · 5 files · 200 diff lines |

## Intent

An empty repository becomes a runnable Python package whose lint, type and test gates all execute and pass, so every later bean has something to be verified against.

## Background

This repository is empty. A Python project needs a declaration of its name, dependencies and tooling before any code can be checked: pyproject.toml is that declaration. Ruff checks style, mypy checks that declared types agree with usage, and pytest runs tests. The gates the factory runs are exactly these three commands, so they must succeed on an empty-but-valid project before any feature exists — otherwise a later failure cannot be attributed to the feature that caused it.

## May write

- `pyproject.toml`
- `src/seating_planner/**`
- `tests/**`
- `.gitignore`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | The package imports cleanly from an installed environment. | `command` `python -c import seating_planner` |
| ac2 | Ruff reports no violations. | `command` `ruff check .` |
| ac3 | Mypy reports no errors. | `command` `mypy src` |
| ac4 | Pytest runs and collects at least one passing test. | `test` `tests/test_scaffold.py::test_package_imports` |

## Constraints

- Python 3.11 or later
- ortools declared as a dependency but not yet imported by any module  
  *checked, not judged:* import `ortools`
- no application logic in this bean

## Non-goals

- no domain models  
  *checked, not judged:* `src/seating_planner/domain/**`
- no solver code  
  *checked, not judged:* `src/seating_planner/solver/**`
- no CI workflow files  
  *checked, not judged:* `.github/workflows/**`, `.gitlab-ci.yml`, `.circleci/**`, `Jenkinsfile`

