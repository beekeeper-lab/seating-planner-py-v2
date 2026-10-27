"""Scaffold test: the package imports cleanly and carries a version."""

import seating_planner


def test_package_imports() -> None:
    """The package is importable and reports a non-empty version string."""
    assert seating_planner.__version__
