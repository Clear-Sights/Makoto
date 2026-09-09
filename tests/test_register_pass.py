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


def test_vendored_register_matches_its_source_when_the_source_is_reachable():
    """docs/REGISTER.md is a copy; measure-zero-dev/REGISTER.md is the source.

    Two copies of one rule is register entry F2, so the drift is checked rather
    than trusted. When the source is not on this machine the test skips: a
    missing source is not evidence the copy is current, and saying so is C2.
    """
    import hashlib

    source = ROOT.parent / "measure-zero-dev" / "REGISTER.md"
    if not source.exists():
        import pytest
        pytest.skip("register source not on this machine; drift NOT-EVALUABLE here")
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(ROOT / "docs" / "REGISTER.md") == digest(source)
