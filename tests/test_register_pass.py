"""The two register runners are bound to the suite.

Writing a rule and leaving it to be run by hand is register entry B7 -- written
or cited, enforced nowhere live -- so these tests are the binding, not a
courtesy. Each asserts both directions: green on the tree as it stands, and red
on a planted defect, so a runner that has stopped deciding anything is visible
(B10, a check that fires on everything says nothing; its mirror, a check that
fires on nothing, says as little).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _run(tool: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "tools" / tool)],
                          capture_output=True, text=True, cwd=ROOT)


def test_merge_pass_is_green_and_the_check_set_is_a_fixpoint():
    r = _run("merge_pass.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the check set is at a fixpoint" in r.stdout


def test_merge_pass_reddens_when_a_witness_is_withdrawn(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import merge_pass

    original = merge_pass.WITNESSES.read_text(encoding="utf-8")
    lines = original.splitlines()
    kept = [lines[0]] + [ln for ln in lines[1:]
                         if not ln.startswith("gate.relative_path_citation\t")]
    planted = tmp_path / "MERGE-WITNESSES.tsv"
    planted.write_text("\n".join(kept) + "\n", encoding="utf-8")
    monkeypatch.setattr(merge_pass, "WITNESSES", planted)

    assert merge_pass.main() == 2


def test_merge_pass_reddens_on_a_witness_for_a_check_that_no_longer_exists(tmp_path, monkeypatch):
    """An orphan witness row is never consulted, so it rots without complaining.

    Found by planting every way this runner should redden rather than the one
    way I first thought of: a single plant shows a runner is not vacuous, never
    that it fires everywhere it should.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import merge_pass

    lines = merge_pass.WITNESSES.read_text(encoding="utf-8").splitlines()
    planted = tmp_path / "orphan.tsv"
    planted.write_text("\n".join(lines + ["gate.deleted\tgate.canon\tan input"]) + "\n",
                       encoding="utf-8")
    monkeypatch.setattr(merge_pass, "WITNESSES", planted)

    assert merge_pass.main() == 2


def test_merge_pass_reddens_when_a_row_names_a_survivor_that_is_gone(tmp_path, monkeypatch):
    """A renamed survivor leaves the row asserting a refutation for nobody."""
    sys.path.insert(0, str(ROOT / "tools"))
    import merge_pass

    lines = merge_pass.WITNESSES.read_text(encoding="utf-8").splitlines()
    planted = tmp_path / "ghost.tsv"
    planted.write_text(
        "\n".join([lines[0]] + [ln.replace("gate.canon_fingerprints ",
                                           "gate.canon_fingerprints gate.ghost ")
                                for ln in lines[1:]]) + "\n", encoding="utf-8")
    monkeypatch.setattr(merge_pass, "WITNESSES", planted)

    assert merge_pass.main() == 2


def test_register_map_carries_every_entry():
    r = _run("register_map.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "every entry carried" in r.stdout


def test_register_map_reddens_on_an_entry_with_no_row(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    lines = register_map.MAP.read_text(encoding="utf-8").splitlines()
    planted = tmp_path / "REGISTER-MAP.tsv"
    planted.write_text("\n".join(ln for ln in lines if not ln.startswith("G5\t")) + "\n",
                       encoding="utf-8")
    monkeypatch.setattr(register_map, "MAP", planted)

    assert register_map.main() == 2


def test_register_map_reddens_on_a_check_the_map_names_nowhere(tmp_path, monkeypatch):
    """A live check with no register home is refused.

    This is the audit's own subject: `B7 RULE WITH NO RUNNER` pointed inward. The plant
    strips every mention of one cited check from the map, so it becomes a runner bound to
    no rule, and the run must stop. Before 2026-09-18 nothing checked this direction and
    eleven checks were named nowhere.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    text = register_map.MAP.read_text(encoding="utf-8")
    assert "gate.unexamined_wall" in text
    planted = tmp_path / "REGISTER-MAP.tsv"
    planted.write_text(text.replace("gate.unexamined_wall", "gate.stale_pass"), encoding="utf-8")
    monkeypatch.setattr(register_map, "MAP", planted)

    assert register_map.main() == 2


def test_register_map_reddens_when_a_longer_id_is_only_prefix_matched(tmp_path, monkeypatch):
    """A cited id must not satisfy a LONGER id that starts with it.

    `gate.canon` is cited for F10 and `gate.canon_fingerprints` for A5/A11. A substring
    test would let the short one home the long one silently, which is exactly `A2
    SURFACE-FORM IDENTITY`. The plant cites only the short form and requires the refusal.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    text = register_map.MAP.read_text(encoding="utf-8")
    planted = tmp_path / "REGISTER-MAP.tsv"
    planted.write_text(text.replace("gate.canon_fingerprints_advisory", "gate.canon")
                           .replace("gate.canon_fingerprints", "gate.canon"), encoding="utf-8")
    monkeypatch.setattr(register_map, "MAP", planted)

    assert register_map.main() == 2


def test_register_map_reddens_on_a_declared_exemption_that_is_not_a_live_check(monkeypatch):
    """A name declared outside the register must be a check that exists."""
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    monkeypatch.setitem(register_map.OUTSIDE_THE_REGISTER, "gate.ghost", "a reason")
    assert register_map.main() == 2


def test_register_map_reddens_on_a_check_both_cited_and_declared_outside(monkeypatch):
    """A check is in the register's subject or declared outside it, never both."""
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    monkeypatch.setitem(register_map.OUTSIDE_THE_REGISTER, "gate.hollow_test", "a reason")
    assert register_map.main() == 2


def test_register_map_reddens_on_a_declared_exemption_with_no_reason(monkeypatch):
    """`B35 UNDECLARED EXEMPTION` applied to this tool's own exemptions: a blank reason is
    an undeclared one."""
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map

    monkeypatch.setitem(register_map.OUTSIDE_THE_REGISTER, "gate.relative_path_citation", "   ")
    assert register_map.main() == 2


# Digest of docs/REGISTER.md as vendored from measure-zero-dev. Re-pin deliberately
# when the register is re-vendored; that edit is the record that a copy moved.
REGISTER_DIGEST = "f64fdf7c6c1d8b574952bc409f067bf138f04db5f3da05b7e34c4402a61d3929"


def test_vendored_register_matches_its_pinned_digest():
    """docs/REGISTER.md is a copy, and this fence pins it.

    Two copies of one rule is register entry F2. The fence compares the copy
    against its own pinned digest, never against the owner's live tree -- the
    rule VENDORED.tsv already states, and the reason it is stated: a check that
    reads another repository only evaluates where that repository happens to
    sit, which is entry E7. This one evaluates everywhere.
    """
    import hashlib

    actual = hashlib.sha256((ROOT / "docs" / "REGISTER.md").read_bytes()).hexdigest()
    assert actual == REGISTER_DIGEST, (
        "docs/REGISTER.md moved without its pin being updated; re-vendor and re-pin"
    )
