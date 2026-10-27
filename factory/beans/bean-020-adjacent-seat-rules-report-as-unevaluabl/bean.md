# bean-020 — Adjacent-seat rules report as unevaluable, never as satisfied

> Generated from `bean.yaml` by `factory/scaffold.sh`. Edit the YAML, not this file.

| Field | Value |
|---|---|
| **Pipeline Tier** | full |
| Status | approved |
| Suggested risk tier | 2 |
| Approved by | Gregg Reed (bulk approval, delegated) |
| Run order | 20 |
| Depends on | bean-019 |
| Size budget | 6 tasks · 7 files · 550 diff lines |

## Intent

A rule the system cannot evaluate — because seat positions were never configured — is reported as unevaluable rather than counted among the rules it satisfied.

## Background

Seat-level layout was deferred for v1 (see the bean set's recorded assumption for PRD §18.3), but FR-034 still allows an adjacent-seat rule to be created, and bean-003 makes such a rule constructible. So the system can hold a rule it has no way to evaluate.
The likely defect is quiet: a rule that generates no constraint contributes nothing to the objective, and code that counts satisfied rules as "active minus violated" will report it satisfied. That is a false success of exactly the kind Principle 5 and Guardrail #6 forbid, and it is worse than a visible failure because the organizer has no reason to doubt it. bean-008 already established unevaluable as a third state; this bean makes adjacent-seat rules use it, and makes an adjacent-seat rule that was *asked to matter* refuse to pass silently.
Run 1 reported the state correctly (rule_states[rule.id] = UNEVALUABLE, a code distinct from VIOLATED and SATISFIED) but attached no explanation anywhere reachable on the result. A bare state code still leaves the organizer exactly where Guardrail #6 says not to leave them: looking at "r-next: unevaluable" with no way to tell, from the result alone, that the reason is "seat positions are not configured" rather than some other unexplained internal refusal. ac5's own text says the result "distinguishes" the two cases, and a distinct code is a minimal reading of that, but the background's "no reason to doubt it" is about being legible to the organizer, not merely machine-distinguishable.
Ready-made fixture for ac6's own test: the one already in this file's own test_unevaluable_reason_is_stated, reused as-is. Two one-seat tables, two guests, two soft rules on the same pair — same_table weight 40, adjacent_seat weight 20. Capacity alone (two one-seat tables, two guests) forces the pair apart in the only feasible chart, so the same_table rule is genuinely violated with nothing else needed to force it; the adjacent_seat rule is unevaluable, no seat positions configured. The solve is feasible; rule_states names the same_table rule VIOLATED and the adjacent_seat rule UNEVALUABLE; the violation list names only the same_table rule. Somewhere reachable from the result (its repr, its to_dict() output, or a field a caller would plausibly read) must contain a human-readable mention of seats, positions, configuration or layout — the actual reason — not only the state code and not only the word "adjacent" (which already appears via the rule's own type name and proves nothing about whether a reason was ever stated).

## May write

- `src/seating_planner/solver/**`
- `src/seating_planner/rules/**`
- `tests/solver/**`
- `tests/rules/**`

## Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| ac1 | An adjacent-seat rule with no seat positions configured is reported unevaluable, not satisfied. | `test` `tests/solver/test_unevaluable.py::test_adjacent_seat_rule_is_unevaluable` |
| ac2 | An unevaluable rule contributes nothing to the soft-constraint score. | `test` `tests/solver/test_unevaluable.py::test_unevaluable_scores_zero` |
| ac3 | Satisfied, violated and unevaluable counts still sum to the number of active rules. | `test` `tests/solver/test_result.py::test_rule_accounting_is_complete` |
| ac4 | A hard adjacent-seat rule blocks optimization with an explanatory error rather than being ignored. | `test` `tests/solver/test_unevaluable.py::test_hard_unevaluable_rule_blocks` |
| ac5 | The result distinguishes unevaluable-because-unconfigured from violated. | `test` `tests/solver/test_unevaluable.py::test_unevaluable_reason_is_stated` |
| ac6 | An unevaluable rule's reason is discoverable from the result in words, not only as a state code -- it says that seat positions are not configured, not merely that the rule is unevaluable. | `test` `tests/solver/test_unevaluable.py::test_unevaluable_rule_states_why_in_words` |

## Constraints

- no seat-level layout implementation in this bean
- a hard rule that cannot be evaluated is never treated as satisfied
- the unevaluable reason is a real, human-readable explanation of what is missing (seat positions), not the word "adjacent" or the rule's own type name standing in for one

## Non-goals

- no seat positions, no seat assignment  
  *checked, not judged:* `src/seating_planner/seats/**`, `src/seating_planner/domain/seat*.py`, `src/seating_planner/solver/seat*.py`

