"""The README makes COUNT claims about makoto's live inventory ("18 pre-checks", "6 end-of-turn
gates"). Those are words makoto emits about itself — so they must be MATERIAL, not illusory. This
binds each stated count to the live loader, and each live gate id to its README mention, so the doc
cannot drift from reality without a test going red. (The gap this closes: before v1.2.0 the README
said "3 end-of-turn gates" while 6 were live, and nothing caught it.)
"""
from __future__ import annotations
import re
from pathlib import Path

from makoto.core.schema import load_prechecks
from makoto.stopchecks import load_stopchecks

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()


def _stated(pattern: str) -> int:
    m = re.search(pattern, README)
    assert m, f"README is missing the count phrase: {pattern!r}"
    return int(m.group(1))


def test_readme_precheck_count_matches_live():
    live = len([p for p in load_prechecks() if p.predicate_module])
    assert _stated(r"\*\*(\d+) pre-checks\*\*") == live


def test_readme_stop_gate_count_matches_live():
    assert _stated(r"\*\*(\d+) end-of-turn gates\*\*") == len(load_stopchecks())


def test_readme_lists_every_live_gate_id():
    for g in load_stopchecks():
        assert g.id in README, f"README does not mention live gate {g.id}"


def test_readme_lists_the_liveness_gate():
    # gate.liveness folded into the Stop tier from the collapsed close-check package; the gate-id
    # listing test above already covers it, but pin its README mention explicitly so the doc keeps
    # describing the code-materiality gate, not only the claim-vs-ledger ones.
    assert "gate.liveness" in {g.id for g in load_stopchecks()}
    assert "gate.liveness" in README


def test_TEETH_stated_parser_would_catch_a_drift():
    # the parser reads a real number, so a stale count (e.g. the old "3") would mismatch the live 6.
    assert _stated(r"\*\*(\d+) end-of-turn gates\*\*") != 3 or len(load_stopchecks()) == 3
