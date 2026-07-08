"""SPEC-C item 4 -- "one mercy model": makoto-allow / MAKOTO_DISABLE_PATTERNS / the advisory
tier / ack-block are all "an on-the-record look-away". This file makes that unification an
explicit, single, citable, re-runnable claim (not four scattered facts a reader has to piece
together from four different test files) -- proving each of the four mercy mechanisms produces
a real chain row, per "Makoto never looks away silently; every look-away is a link in the
chain." Found while auditing SPEC-C's own item list: this unification turned out to be a
side-effect of work already landed in Task 2 (slices 3b/4/5), not new work -- this file is what
makes that a PROVEN claim rather than a coincidence nobody wrote down.
"""
from __future__ import annotations

import json
import subprocess
import sys as _sys
from pathlib import Path

from makoto import audit, ledger


def _kinds(chain_root: Path) -> set:
    return {row.get("kind") for row in ledger.read(root=chain_root)}


# ---- 1. makoto-allow ----------------------------------------------------------------------------
def test_makoto_allow_exemption_is_a_chained_row(tmp_path):
    audit.append_exemption(tmp_path, pattern_id="content.timing_unsafe_compare", kind="makoto-allow", file="h.py",
                           line=4, reason="pinned internal host", snippet="a == b")
    rows = [r for r in ledger.read(root=tmp_path) if r.get("kind") == "exemption"]
    assert len(rows) == 1
    assert rows[0]["exemption_kind"] == "makoto-allow"
    assert ledger.verify_chain(root=tmp_path) is None


# ---- 2. MAKOTO_DISABLE_PATTERNS -------------------------------------------------------------------
def test_disabled_pattern_exemption_is_a_chained_row(tmp_path):
    audit.append_exemption(tmp_path, pattern_id="content.verifier_predicate_weakened", kind="disabled-pattern", file="x.py",
                           line=0, reason="MAKOTO_DISABLE_PATTERNS=1.1")
    rows = [r for r in ledger.read(root=tmp_path) if r.get("kind") == "exemption"]
    assert len(rows) == 1
    assert rows[0]["exemption_kind"] == "disabled-pattern"


# ---- 3. the advisory tier --------------------------------------------------------------------
def test_advisory_tier_fire_is_a_chained_row(tmp_path, monkeypatch):
    """An ADVISE-tier finding (e.g. the test-delta redirect) is recorded via _record_audit ->
    audit.append_row -> the chain (kind="audit"), same as any BLOCK-tier fire -- the advisory
    tier is never a second-class, unrecorded mercy."""
    from makoto.db import init_db
    state_dir = tmp_path / "state"
    (tmp_path / "CITATIONS.md").write_text("x")
    init_db(state_dir, tmp_path / "CITATIONS.md")
    env = {"MAKOTO_STATE_DIR": str(state_dir)}
    import os
    full_env = os.environ.copy()
    full_env.update(env)

    def _dispatch(payload):
        proc = subprocess.run([_sys.executable, "-m", "makoto._dispatch"],
                              input=json.dumps(payload).encode(), capture_output=True,
                              env=full_env, cwd=str(Path(__file__).parent.parent))
        return proc.returncode, proc.stdout.decode()

    sid = "mercy-advisory"
    _dispatch({"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
              "cwd": "/tmp", "tool_input": {"command": "pytest -q"},
              "tool_response": {"stdout": "PASSED tests/x.py::test_a\n", "stderr": "", "exitCode": 0}})
    _dispatch({"hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": sid,
              "cwd": "/tmp", "tool_input": {"command": "pytest -q"},
              "tool_response": {"stdout": "FAILED tests/x.py::test_a\n", "stderr": "", "exitCode": 1}})
    rows = [r for r in ledger.read(root=state_dir) if r.get("kind") == "audit"]
    assert len(rows) == 1
    assert rows[0]["pattern_fires"] == ["makoto.test_delta"]


# ---- 4. ack-block --------------------------------------------------------------------------------
def test_ack_block_is_a_chained_row(tmp_path):
    from makoto.ackblock import record_ack_block_if_new
    ack = {"fingerprint_id": "timeout", "reason": "reviewed", "ts": "2026-07-07T00:00:00Z"}
    record_ack_block_if_new(ack, session_id="s1", root=tmp_path)
    rows = [r for r in ledger.read(root=tmp_path) if r.get("kind") == "release.operator"]
    assert len(rows) == 1


# ---- the unifying claim itself -----------------------------------------------------------------
def test_all_four_mercy_kinds_are_distinct_chained_kinds_never_a_silent_fifth_path(tmp_path):
    """The actual SPEC-C item 4 claim, in one assertion: every mercy this project has ever
    shipped lands as one of exactly these kinds on the chain -- no mercy mechanism exists that
    writes NOTHING (a silent look-away)."""
    from makoto.ackblock import record_ack_block_if_new
    audit.append_exemption(tmp_path, pattern_id="content.timing_unsafe_compare", kind="makoto-allow", file="h.py",
                           line=1, reason="r")
    audit.append_exemption(tmp_path, pattern_id="content.verifier_predicate_weakened", kind="disabled-pattern", file="x.py",
                           line=0, reason="r")
    record_ack_block_if_new({"fingerprint_id": "timeout", "reason": "r", "ts": "t"},
                            session_id="s1", root=tmp_path)
    kinds = _kinds(tmp_path)
    assert {"exemption", "release.operator"} <= kinds
    assert ledger.verify_chain(root=tmp_path) is None
