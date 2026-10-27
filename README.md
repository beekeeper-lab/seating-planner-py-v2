# seating-planner-py-v2

A wedding seating optimizer, built by the [Local Dark Factory](https://github.com/beekeeper-lab) line
rather than by hand. **This repository is disposable**: it is a measurement fixture, and it is
expected to be deleted and rebuilt from the same frozen requirements whenever the line changes.

This is a from-scratch rebuild of `beekeeper-lab/seating-planner-py`, run against the same
bean set (`benchmark/seating-planner/bean-sets/v1`, current state — including every amendment
and fix made during the first build) and the same hidden test suite, to measure whether fixes
made to the factory's own tooling during the first build (a recurring task-ordering defect in
generated `tasks.yaml`, the judge's demotion to advisory-only, corrected size-budget heuristics)
actually reduce the operator intervention the first build needed. The original repository is left
untouched as the baseline.

Nothing here is written by a person. The `factory/` directory is the exception — it is the
control surface, generated from the factory repo, and it is what tells the line what it may do:

| Path | What it is |
|---|---|
| `factory/repo.yaml` | What the line may do to this repo. `merge_mode: human_required` — the line opens pull requests and cannot merge them. |
| `factory/risk-policy.yaml` | Which paths need how much scrutiny. The controller computes a bean's tier from the paths its diff actually touched. |
| `factory/gates.lock.yaml` | The gates, pinned to a container image by digest, with the tool versions asserted at startup. |
| `factory/beans/` | The approved work items. The line reads these; it never writes them. |
| `factory/templates/` | The HTML templates the two documents are rendered into. |
| `factory/specs/`, `factory/impl/` | The line's own output: what it planned, and what it built. |

Every change arrives as a pull request carrying a rendered spec, a rendered implementation-detail
document, and three independent audit verdicts from a different model family than the one that
wrote the code. A human merges. That is the whole arrangement.
