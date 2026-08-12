"""A registered live check must have a test that names its implementation or id."""
from __future__ import annotations

from pathlib import Path

from makoto.substrate._loader import load_checks


REPO = Path(__file__).resolve().parent.parent
TESTS = tuple((REPO / "tests").rglob("test_*.py"))


def test_every_live_check_has_a_direct_exerciser():
    """A catalog row without a named exercising test is decoration, not protection."""
    missing = []
    for check in load_checks():
        module = (check.predicate_module or "").rsplit(".", 1)[-1]
        is_named = any(
            check.id in test.read_text(encoding="utf-8")
            or (module and module in test.read_text(encoding="utf-8"))
            for test in TESTS
        )
        if not is_named:
            missing.append(check.id)
    assert missing == [], f"live checks without a direct exerciser: {missing}"
