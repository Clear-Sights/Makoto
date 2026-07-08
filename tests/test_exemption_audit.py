"""makoto-follows-makoto: a `makoto-allow` exemption of a REAL match must leave an on-the-record,
auditable trace (claim C3). Red-stated before the factories were wired to record — these failed on
`len(rows) == 1` (the suppression was silent), proving the gap the verdict flagged as R5b."""
from __future__ import annotations
import json
import sqlite3
import tempfile
from pathlib import Path

import makoto.db as vdb
import makoto._dispatch  # noqa: F401 — importing the L3 orchestrator installs the exemption sink
from makoto.schema import PreCheck, load_prechecks
from makoto import audit
from makoto.lib import factories


def _state(tmp: Path) -> Path:
    cit = tmp / "CITATIONS.md"
    cit.write_text("Smith 2020\n")
    vdb.init_db(tmp / "st", cit)
    return tmp / "st"


def _evt(fp: str, content: str, sid: str = "s1", tool: str = "Write") -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": sid, "tool_name": tool,
            "tool_input": {"file_path": fp, "content": content}}


def _run(pid: str, evt: dict, conn):
    import importlib
    # SPEC-5: resolve via the real catalog's predicate_module (flat makoto.checks, descriptive
    # names -- no longer derivable from the pattern id).
    _mod_path = next(p.predicate_module for p in load_prechecks() if p.id == pid)
    mod = importlib.import_module(_mod_path)
    pat = PreCheck(id=pid, fire_level="error", description="x", retry_hint="y")
    return mod.predicate(current_event=evt, history=[], pattern=pat, conn=conn)


def test_exempted_real_match_is_recorded(tmp_path):
    """1.26 verify=False + makoto-allow reason -> still exempt (no block) BUT one exemption row."""
    st = _state(tmp_path)
    conn = sqlite3.connect(str(st / "makoto.db"))
    content = ("import requests\n"
               "requests.get(u, verify=False)  # makoto-allow: pinned internal dev host\n")
    out = _run("content.cert_verify_disabled", _evt("client.py", content), conn)
    assert out is None, "the marker must still exempt (no block)"
    rows = list(audit.read_exemptions(st))
    assert len(rows) == 1, "an exempted REAL match must leave exactly one on-record exemption row"
    r = rows[0]
    assert r["pattern_id"] == "content.cert_verify_disabled"
    assert r["kind"] == "makoto-allow"
    assert "pinned internal dev host" in r["reason"]
    assert r["file"] == "client.py"
    assert r["session_id"] == "s1"
    conn.close()


def test_marker_without_a_real_match_records_nothing(tmp_path):
    """precision: a makoto-allow marker on clean code is NOT a suppression -> no noise row."""
    st = _state(tmp_path)
    conn = sqlite3.connect(str(st / "makoto.db"))
    content = "import requests\nrequests.get(u)  # makoto-allow: nothing wrong here\n"
    out = _run("content.cert_verify_disabled", _evt("client.py", content), conn)
    assert out is None
    assert list(audit.read_exemptions(st)) == [], "no real match -> no exemption noise"
    conn.close()


def test_pure_unit_call_without_conn_writes_nothing(tmp_path, monkeypatch):
    """conn=None (a direct unit call) stays a pure detector: no state dir is created or written."""
    target = tmp_path / "should_not_exist"
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(target))
    content = "requests.get(u, verify=False)  # makoto-allow: x\n"
    out = _run("content.cert_verify_disabled", _evt("client.py", content), None)
    assert out is None
    assert not target.exists(), "a pure unit call must not touch any state dir"


def test_regex_factory_path_also_records(tmp_path):
    """the OTHER factory (regex_file_predicate, 1.4 audit_skip) records its exempted match too."""
    st = _state(tmp_path)
    conn = sqlite3.connect(str(st / "makoto.db"))
    # reason deliberately free of an "ADR" token: 1.4 has its OWN exempt_rx (ADR backlink) that
    # would carve out silently before the makoto-allow path — we want the makoto-allow branch here.
    content = "audit_skip = true  # makoto-allow: legacy flag, owner aware\n"
    out = _run("content.integrity_suppression_flag", _evt("config.toml", content), conn)
    assert out is None
    rows = list(audit.read_exemptions(st))
    assert len(rows) == 1 and rows[0]["pattern_id"] == "content.integrity_suppression_flag"
    assert "owner aware" in rows[0]["reason"]
    conn.close()


def test_disabled_pattern_suppression_is_recorded(tmp_path, monkeypatch):
    """MAKOTO_DISABLE_PATTERNS muting a pattern that keyword-hits the payload leaves a record —
    the silent-disable gap closed; parity with the already-audited MAKOTO_DISABLE_GATES."""
    from makoto._dispatch import _run_predicates
    from makoto.schema import load_prechecks
    st = _state(tmp_path)
    conn = sqlite3.connect(str(st / "makoto.db"))
    pat = next(p for p in load_prechecks() if p.predicate_module and p.keywords)
    kw = pat.keywords[0]
    monkeypatch.setenv("MAKOTO_DISABLE_PATTERNS", pat.id)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s2", "tool_name": "Bash",
               "tool_input": {"command": kw + " something"}}
    _run_predicates(conn, payload, [], 1, st, json.dumps(payload))
    rows = [r for r in audit.read_exemptions(st) if r["kind"] == "disabled-pattern"]
    assert any(r["pattern_id"] == pat.id for r in rows), "a muted keyword-hit pattern must be recorded"
    conn.close()


def test_makoto_allow_reason_extracts_and_trims(tmp_path):
    """the reason capture: text after the colon, comment-close tokens and overflow trimmed."""
    assert factories.makoto_allow_reason("x  # makoto-allow: pinned dev host") == "pinned dev host"
    assert factories.makoto_allow_reason("<!-- makoto-allow: real source -->") == "real source"
    assert factories.makoto_allow_reason("no marker") is None
    assert len(factories.makoto_allow_reason("# makoto-allow: " + "z" * 500)) == 200


def test_append_exemption_round_trips_through_reader(tmp_path):
    """append_exemption writes a row read_exemptions yields back — the writer/reader pair is whole."""
    st = _state(tmp_path)
    audit.append_exemption(st, pattern_id="content.timing_unsafe_compare", kind="makoto-allow", file="h.py", line=4,
                           reason="constant-time compare not needed here", snippet="a == b")
    rows = list(audit.read_exemptions(st))
    assert len(rows) == 1 and rows[0]["pattern_id"] == "content.timing_unsafe_compare" and rows[0]["line"] == 4


def test_append_exemption_also_chain_appends_with_renamed_kind(tmp_path):
    """Task 2 slice 4 (Fable-flagged gap, closed): append_exemption's row also lands in the same
    state_root's chain, verifiable via verify_chain. The chain row's STRUCTURAL kind is
    'exemption'; the original suppression-mechanism kind ('makoto-allow'/'disabled-pattern') is
    renamed to exemption_kind in the chain payload only, so it never collides with the chain's
    own kind field -- the exemptions.jsonl line itself is untouched (still keyed 'kind')."""
    from makoto import ledger as _ledger
    st = _state(tmp_path)
    audit.append_exemption(st, pattern_id="content.timing_unsafe_compare", kind="makoto-allow", file="h.py", line=4,
                           reason="constant-time compare not needed here", snippet="a == b")
    assert _ledger.verify_chain(root=st) is None
    rows = _ledger.read(root=st)
    assert len(rows) == 1
    assert rows[0]["kind"] == "exemption"
    assert rows[0]["exemption_kind"] == "makoto-allow"
    assert rows[0]["pattern_id"] == "content.timing_unsafe_compare"
    exempt_rows = list(audit.read_exemptions(st))
    assert exempt_rows[0]["kind"] == "makoto-allow"          # untouched on the jsonl side


def test_set_exemption_sink_is_restorable(tmp_path):
    """set_exemption_sink installs/clears the injected recorder; the dispatcher's is the live one."""
    saved = factories._EXEMPTION_SINK
    try:
        factories.set_exemption_sink(None)
        assert factories._EXEMPTION_SINK is None
    finally:
        factories.set_exemption_sink(saved)
    assert factories._EXEMPTION_SINK is saved


def test_no_disable_env_means_no_suppression_work(tmp_path):
    """default case: MAKOTO_DISABLE_PATTERNS unset -> no disabled-pattern rows ever written."""
    from makoto._dispatch import _run_predicates
    from makoto.schema import load_prechecks
    st = _state(tmp_path)
    conn = sqlite3.connect(str(st / "makoto.db"))
    pat = next(p for p in load_prechecks() if p.predicate_module and p.keywords)
    payload = {"hook_event_name": "PreToolUse", "session_id": "s3", "tool_name": "Bash",
               "tool_input": {"command": pat.keywords[0] + " something"}}
    _run_predicates(conn, payload, [], 1, st, json.dumps(payload))
    assert [r for r in audit.read_exemptions(st) if r["kind"] == "disabled-pattern"] == []
    conn.close()
