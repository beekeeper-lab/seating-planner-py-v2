"""API-stability pin for the solver entry point and the construction/run split (ac3).

One test: signature pins on ``solve_hard`` and ``optimize``, and — the
half that only the refactored tree satisfies — an ast pin that one module
in the package creates CP-SAT variables without ever naming ``CpSolver``
while a different module names ``CpSolver`` without creating variables.
On the unrefactored tree both facts held only in ``hard.py`` together, so
the ast half is what fails there if the refactor is reverted.
"""

import ast
import inspect
from pathlib import Path

import seating_planner.solver
from seating_planner.solver import optimize, solve_hard

_POS_OR_KW = inspect.Parameter.POSITIONAL_OR_KEYWORD
_KW_ONLY = inspect.Parameter.KEYWORD_ONLY


def test_public_entry_point_unchanged():
    hard_params = list(inspect.signature(solve_hard).parameters.values())
    assert [p.name for p in hard_params] == [
        "event",
        "config",
        "mode",
        "current_assignments",
        "move_limit",
        "unlocked_guest_ids",
    ]
    assert hard_params[0].kind is _POS_OR_KW
    assert hard_params[0].default is inspect.Parameter.empty
    assert hard_params[1].kind is _POS_OR_KW
    assert hard_params[1].default is None
    assert hard_params[2].kind is _KW_ONLY
    assert hard_params[2].default is inspect.Parameter.empty
    for baseline in hard_params[3:]:
        assert baseline.kind is _KW_ONLY
        assert baseline.default is None

    opt_params = list(inspect.signature(optimize).parameters.values())
    assert [p.name for p in opt_params] == [
        "event",
        "config",
        "mode",
        "saved_chart",
        "move_limit",
    ]
    assert opt_params[0].kind is _POS_OR_KW
    assert opt_params[0].default is inspect.Parameter.empty
    assert opt_params[1].kind is _POS_OR_KW
    assert opt_params[1].default is None
    assert opt_params[2].kind is _KW_ONLY
    assert opt_params[2].default is inspect.Parameter.empty
    assert opt_params[3].kind is _KW_ONLY
    assert opt_params[3].default is inspect.Parameter.empty
    assert opt_params[4].kind is _KW_ONLY
    assert opt_params[4].default is None

    solver_dir = Path(seating_planner.solver.__file__).parent
    builder_module: str | None = None
    solver_module: str | None = None
    for path in sorted(solver_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        creates_var = False
        names_cp_solver = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("new_bool_var", "new_int_var")
            ):
                creates_var = True
            if (isinstance(node, ast.Name) and node.id == "CpSolver") or (
                isinstance(node, ast.Attribute) and node.attr == "CpSolver"
            ):
                names_cp_solver = True
        if creates_var and not names_cp_solver:
            builder_module = path.name
        if names_cp_solver and not creates_var:
            solver_module = path.name
    assert builder_module, "no module creates CP-SAT variables without naming CpSolver"
    assert solver_module, "no module names CpSolver without creating CP-SAT variables"
