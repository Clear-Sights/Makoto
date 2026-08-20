"""SPEC-C item 4 -- "one mercy model": makoto-allow / MAKOTO_DISABLE_PATTERNS / the advisory
tier / release.operator are all "an on-the-record look-away". This file makes that unification an
explicit, single, citable, re-runnable claim (not four scattered facts a reader has to piece
together from four different test files) -- proving each of the four mercy mechanisms produces
a real chain row, per "Makoto never looks away silently; every look-away is a link in the
chain."

DERIVATION DISCIPLINE (the point of the 2026-08 rewrite): every mercy row below is produced by
the code that DERIVES the mercy -- a real `python -m makoto.dispatch` subprocess for the
makoto-allow sink (dispatch._record_exemption_sink via the factories exemption hook), for the
MAKOTO_DISABLE_PATTERNS mute loop (dispatch's `muted` loop) and for the advisory tier
(_record_audit), and the real `canon_fingerprint_block_gate` transcript-ack rederivation for
release.operator. The previous revision called `audit.append_exemption` /
`record_ack_block_if_new` directly with the `kind` string hand-supplied, so the derivation call
sites could be deleted -- or their `except Exception: pass` swallows could eat every row -- and
three of the four "proofs" stayed green. Each mercy test also carries its no-mercy CONTROL (the
same input without the marker/env/ack must DENY or fire), so a mercy row produced for the wrong
reason cannot pass.
"""
from __future__ import annotations

import json

from makoto.state import ledger
from tests.conftest import _setup_state, _run_dispatch

# content.verifier_predicate_weakened fires on a Write of a loose-comparator verifier -- the
# known-firing payload test_dispatch.py already pins. The allowed twin differs ONLY by the
# structured `# makoto-allow: <reason>` marker.
_VERIFIER_PATH = "constitution/integrity/checks/myverifier.py"
_WEAK_VERIFIER = 'def check(x):\n    return x.startswith("ok")\n'
_WEAK_VERIFIER_ALLOWED = (
    'def check(x):\n    return x.startswith("ok")  # makoto-allow: pinned prefix protocol, reviewed\n')


def _substate(tmp_path, name):
    """A separate state root under tmp_path (conftest._setup_state needs the dir to exist)."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return _setup_state(d)


def _pre_write(state_dir, content, sid, extra_env=None):
    return _run_dispatch(state_dir, {
        "hook_event_name": "PreToolUse", "session_id": sid, "cwd": "/tmp",
        "tool_input": {"file_path": _VERIFIER_PATH, "content": content},
    }, extra_env=extra_env)


def _kinds(chain_root) -> set:
    return {row.get("kind") for row in ledger.read(root=chain_root)}


def _exemptions(chain_root):
    return [r for r in ledger.read(root=chain_root) if r.get("kind") == "exemption"]


# ---- 1. makoto-allow ----------------------------------------------------------------------------
def test_makoto_allow_exemption_is_a_chained_row(tmp_path):
    """The REAL sink: dispatch fires content.verifier_predicate_weakened, the in-content
    `# makoto-allow: <reason>` marker suppresses the confirmed match, and
    dispatch._record_exemption_sink chains the look-away. Control first: without the marker the
    same payload DENIES, so the silence below is the marker's doing, not a dead check."""
    control = _substate(tmp_path, "control")
    rc, out = _pre_write(control, _WEAK_VERIFIER, "mercy-allow-control")
    assert '"deny"' in out, f"control payload must fire the check; got {out!r}"

    state = _substate(tmp_path, "mercy")
    rc, out = _pre_write(state, _WEAK_VERIFIER_ALLOWED, "mercy-allow")
    assert rc == 0 and out == "", f"marker must suppress the deny; got {out!r}"
    rows = _exemptions(state)
    assert len(rows) == 1
    assert rows[0]["exemption_kind"] == "makoto-allow"
    assert rows[0]["pattern_id"] == "content.verifier_predicate_weakened"
    assert ledger.verify_chain(root=state) is None


# ---- 2. MAKOTO_DISABLE_PATTERNS -------------------------------------------------------------------
def test_disabled_pattern_exemption_is_a_chained_row(tmp_path):
    """The REAL mute loop: MAKOTO_DISABLE_PATTERNS in the dispatch subprocess's environment mutes
    a would-have-been candidate, and dispatch's `muted` loop chains the suppression BEFORE any
    predicate runs. Control: the same payload without the env var denies."""
    control = _substate(tmp_path, "control")
    rc, out = _pre_write(control, _WEAK_VERIFIER, "mercy-mute-control")
    assert '"deny"' in out

    state = _substate(tmp_path, "mercy")
    rc, out = _pre_write(state, _WEAK_VERIFIER, "mercy-mute",
                         extra_env={"MAKOTO_DISABLE_PATTERNS": "content.verifier_predicate_weakened"})
    assert rc == 0 and out == "", f"muted pattern must not deny; got {out!r}"
    rows = _exemptions(state)
    assert len(rows) == 1
    assert rows[0]["exemption_kind"] == "disabled-pattern"
    assert "MAKOTO_DISABLE_PATTERNS" in rows[0]["reason"]
    assert ledger.verify_chain(root=state) is None


# ---- 3. the advisory tier --------------------------------------------------------------------
def test_advisory_tier_fire_is_a_chained_row(tmp_path):
    """An ADVISE-tier finding (e.g. the test-delta redirect) is recorded via _record_audit ->
    audit.append_row -> the chain (kind="audit"), same as any BLOCK-tier fire -- the advisory
    tier is never a second-class, unrecorded mercy."""
    state = _setup_state(tmp_path)
    sid = "mercy-advisory"
    for res in ({"stdout": "PASSED tests/x.py::test_a\n", "stderr": "", "exitCode": 0},
                {"stdout": "FAILED tests/x.py::test_a\n", "stderr": "", "exitCode": 1}):
        _run_dispatch(state, {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                              "session_id": sid, "cwd": "/tmp",
                              "tool_input": {"command": "pytest -q"}, "tool_response": res})
    rows = [r for r in ledger.read(root=state) if r.get("kind") == "audit"]
    assert len(rows) == 1
    assert rows[0]["pattern_fires"] == ["makoto.test_delta"]


# ---- 4. release.operator----------------------------------------------------------------------------
def _destructive_row():
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "rm -rf build/"}, "tool_response": {}}}


def _ack_transcript(tmp_path, name):
    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps({
        "type": "user",
        "message": {"role": "user",
                    "content": f"makoto release.operator {name}: reviewed, the rm -rf was sanctioned"},
        "timestamp": "2026-07-08T00:00:00Z"}) + "\n", encoding="utf-8")
    return p


def test_ack_block_is_a_chained_row(tmp_path):
    """The REAL rederivation: canon_fingerprint_block_gate fires notestedit_destruct (recorded),
    then a genuine host-written ack turn in the transcript discharges it on the next Stop -- and
    it is the GATE (canonFingerprints.py's find_ack_block -> record_ack_block_if_new call) that
    chains the release.operator row, not this test. Control: the first firing, before any ack,
    must BLOCK."""
    from makoto.checks.canonFingerprints import canon_fingerprint_block_gate
    state = _setup_state(tmp_path)
    first = canon_fingerprint_block_gate("", [_destructive_row()], session_id="s1", state_root=state)
    msg = next(f.message for f in first if f.message.startswith("canon.notestedit_destruct:"))
    assert msg, "control: the fingerprint must fire before any ack exists"
    ledger.append({"kind": "audit", "session_id": "s1", "ts": "2026-07-07T00:00:00Z",
                   "pattern_fires": ["gate.canon_fingerprints"],
                   "findings": [{"message": msg}]}, root=state)
    p = _ack_transcript(tmp_path, "notestedit_destruct")
    second = canon_fingerprint_block_gate("", [_destructive_row()], transcript_path=str(p),
                                          session_id="s1", state_root=state)
    assert not any(f.message.startswith("canon.notestedit_destruct:") for f in second)
    rows = [r for r in ledger.read(root=state) if r.get("kind") == "release.operator"]
    assert len(rows) == 1
    assert rows[0]["fingerprint_id"] == "notestedit_destruct"
    assert ledger.verify_chain(root=state) is None


# ---- the unifying claim itself -----------------------------------------------------------------
def test_all_four_mercy_kinds_are_distinct_chained_kinds_never_a_silent_fifth_path(tmp_path):
    """The actual SPEC-C item 4 claim, in one assertion set: every mercy this project ships lands
    on ONE chain as one of exactly these kinds, each produced here by its REAL derivation path --
    makoto-allow and disabled-pattern (kind="exemption", distinguished by exemption_kind), the
    advisory tier (kind="audit"), and release.operator. The kind-set assertion is EQUALITY, not
    subset: an unexpected kind appearing on the chain reds this test rather than sliding by, and
    a mercy path that stopped writing its row reds it too. (Honest limit, stated: a hypothetical
    fifth mercy mechanism that writes NOTHING cannot be detected by any chain assertion -- what
    this pins is that all four SHIPPED mechanisms write, on the same chain, distinguishably.)"""
    from makoto.checks.canonFingerprints import canon_fingerprint_block_gate
    state = _setup_state(tmp_path)
    sid = "mercy-all"
    # 1: makoto-allow via real dispatch
    rc, out = _pre_write(state, _WEAK_VERIFIER_ALLOWED, sid)
    assert out == ""
    # 2: disabled-pattern via real dispatch + env
    rc, out = _pre_write(state, _WEAK_VERIFIER, sid,
                         extra_env={"MAKOTO_DISABLE_PATTERNS": "content.verifier_predicate_weakened"})
    assert out == ""
    # 3: the advisory tier via real dispatch (test-delta redirect -> kind="audit")
    for res in ({"stdout": "PASSED tests/x.py::test_a\n", "stderr": "", "exitCode": 0},
                {"stdout": "FAILED tests/x.py::test_a\n", "stderr": "", "exitCode": 1}):
        _run_dispatch(state, {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                              "session_id": sid, "cwd": "/tmp",
                              "tool_input": {"command": "pytest -q"}, "tool_response": res})
    # 4: release.operator via the real gate rederivation
    first = canon_fingerprint_block_gate("", [_destructive_row()], session_id=sid, state_root=state)
    msg = next(f.message for f in first if f.message.startswith("canon.notestedit_destruct:"))
    ledger.append({"kind": "audit", "session_id": sid, "ts": "2026-07-07T00:00:00Z",
                   "pattern_fires": ["gate.canon_fingerprints"],
                   "findings": [{"message": msg}]}, root=state)
    canon_fingerprint_block_gate("", [_destructive_row()],
                                 transcript_path=str(_ack_transcript(tmp_path, "notestedit_destruct")),
                                 session_id=sid, state_root=state)

    rows = list(ledger.read(root=state))
    # EXACT kind set: the four mercy kinds plus the chain's own testrun bookkeeping rows the
    # advisory flow necessarily records (pytest PostToolUse runs). Anything else appearing on
    # the chain -- or any mercy kind missing -- fails here.
    assert {r.get("kind") for r in rows} == {"exemption", "audit", "testrun", "release.operator"}
    assert ({r.get("exemption_kind") for r in rows if r.get("kind") == "exemption"}
            == {"makoto-allow", "disabled-pattern"})
    advisory = [r for r in rows if r.get("kind") == "audit"
                and r.get("pattern_fires") == ["makoto.test_delta"]]
    assert len(advisory) == 1, "the advisory tier's own audit row must be on the chain"
    assert [r.get("fingerprint_id") for r in rows if r.get("kind") == "release.operator"] \
        == ["notestedit_destruct"]
    assert ledger.verify_chain(root=state) is None
