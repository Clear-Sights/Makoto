"""Every shipped exemption or advisory decision is recorded on the same audit chain.

Exercise each through real dispatch, with a blocking control for the exemptions.
"""
from __future__ import annotations


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


# ---- the unifying claim itself -----------------------------------------------------------------
def test_all_mercy_mechanisms_are_distinct_on_the_same_chain(tmp_path):
    """Both exemptions and the advisory tier record their real derivation paths."""
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
    rows = list(ledger.read(root=state))
    assert {r.get("kind") for r in rows} == {"exemption", "audit", "testrun"}
    assert ({r.get("exemption_kind") for r in rows if r.get("kind") == "exemption"}
            == {"makoto-allow", "disabled-pattern"})
    advisory = [r for r in rows if r.get("kind") == "audit"
                and r.get("pattern_fires") == ["makoto.test_delta"]]
    assert len(advisory) == 1, "the advisory tier's own audit row must be on the chain"
    assert ledger.verify_chain(root=state) is None
