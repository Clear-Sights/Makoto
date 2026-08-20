"""The `makoto-allow` escape hatch means the same thing everywhere it is honored.

§7.5b: the marker is `makoto-allow: <reason>` -- a colon and a non-empty rationale. A bare
`makoto-allow` does not exempt, because "an exemption without an on-the-record rationale is a
reasonless laundering token, which is itself an empty word". That is the rule makoto INSTALLS
INTO THE USER'S CLAUDE.md ("an on-the-record, auditable rationale, never a disguise"), and the
rule `makoto_allowed`/`_MAKOTO_ALLOW_RX` enforces for every factory-built content check.

Two AST engines -- `hollowTest` and `deadPureStatement` -- hand-rolled the test instead:
`"makoto-allow" in line.lower()`. So a reasonless `# makoto-allow` suppressed a hollow-test or
dead-statement finding that the identical marker could not suppress anywhere else, while BOTH
checks' own finding text tells the author to write `# makoto-allow: <reason>`. The escape hatch
was strictly laxer than the rule, on the one path where laxness is a bypass rather than a
nuisance -- the same shape as the decayed `_makoto_managed` flag: a marker asserting an audit
trail, accepted without one.

One concept, one predicate. Pinned across every honoring site at once so a future site cannot
quietly reintroduce a second strictness.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from makoto.checks import deadPureStatement, hollowTest
from makoto.kit import makoto_allowed

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "plugin" / "makoto" / "checks"

REASONED = "# makoto-allow: intentional, reviewed 2026-08-14"
BARE = "# makoto-allow"
COLON_ONLY = "# makoto-allow:"


def test_the_canonical_predicate_requires_a_reason():
    assert makoto_allowed(REASONED) is True
    assert makoto_allowed(BARE) is False
    assert makoto_allowed(COLON_ONLY) is False


@pytest.mark.parametrize("marker,exempts", [(REASONED, True), (BARE, False), (COLON_ONLY, False)])
def test_hollow_test_honors_the_canonical_marker(marker, exempts):
    assert hollowTest._allowed(1, [marker]) is exempts


def test_hollow_test_agrees_with_the_canonical_predicate():
    for marker in (REASONED, BARE, COLON_ONLY, "no marker here"):
        assert hollowTest._allowed(1, [marker]) == makoto_allowed(marker), marker


def test_dead_pure_statement_honors_the_canonical_marker():
    """`deadPureStatement`'s `_allowed` is a closure over the file's lines, so it is exercised
    through `analyze_file` -- the real path, not a reimplementation of it."""
    unmarked = "def f():\n    1 + 2\n"
    assert deadPureStatement.analyze_file(unmarked, "m.py") != [], (
        "control: the construct must actually fire, or the exemption cases below prove nothing")
    assert deadPureStatement.analyze_file(f"def f():\n    1 + 2  {REASONED}\n", "m.py") == []
    assert deadPureStatement.analyze_file(f"def f():\n    1 + 2  {BARE}\n", "m.py") != [], (
        "a reasonless marker must not exempt a dead statement")


def test_a_reasoned_marker_still_exempts_a_hollow_test():
    """PAIRED. The hatch must keep working -- tightening it into uselessness would be the same
    defect with the sign flipped."""
    assert hollowTest._allowed(1, [f"def test_x(): pass  {REASONED}"]) is True


def test_no_check_hand_rolls_the_marker_test():
    """By construction, across the whole catalog: the marker's spelling lives in exactly one
    place. A bare `"makoto-allow" in ...` membership test anywhere in `makoto/checks/` is the
    divergence this file exists to prevent, so it is barred structurally rather than by review."""
    offenders = []
    for path in sorted(_CHECKS_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Compare)
                    and any(isinstance(op, ast.In) for op in node.ops)
                    and isinstance(node.left, ast.Constant)
                    and isinstance(node.left.value, str)
                    and "makoto-allow" in node.left.value):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"hand-rolled `makoto-allow` membership test(s) at {offenders} -- use "
        f"makoto.vocab._MAKOTO_ALLOW_RX (§7.5b requires a colon and a reason)")
