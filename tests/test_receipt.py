"""Claim-rooted receipt tests.

Only persisted claim nodes are assertions.  Test runs, deeds, verdicts, and other evidence rows
remain evidence; they never become claims merely because a receipt can cite them.
"""
from __future__ import annotations

import json
import sqlite3

from makoto.record import claim_graph, ledger
from makoto.record.receipt import emit_receipt


def _persist_action_claim(root, *, session_id="s1", event_id=2):
    conn = sqlite3.connect(":memory:", isolation_level=None)
    history = [(event_id - 1, "t", "PostToolUse", "/repo", json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "scripts/deploy.sh"},
        "tool_response": {"exitCode": 0},
    }))]
    stop = {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "cwd": "/repo",
        "last_assistant_message": "I ran `scripts/deploy.sh`.",
    }
    built = claim_graph.build_stop_graph(
        conn, stop, history, event_id=event_id, root=root,
    )
    conn.close()
    return built


def test_absent_chain_is_a_vacuous_all_zero_receipt(tmp_path):
    receipt = emit_receipt(root=tmp_path)
    assert receipt["verified_through"] is None
    assert receipt["claims"] == []
    assert receipt["claim_count"] == 0
    assert receipt["trace_bound_count"] == 0
    assert receipt["exemption_count"] == 0


def test_evidence_kinds_are_never_misnamed_as_claims(tmp_path):
    for kind in ("testrun", "audit", "touched", "certified-fact", "verdict", "deed"):
        ledger.append({"kind": kind, "key": kind, "session_id": "s1"}, root=tmp_path)
    assert emit_receipt(session_id="s1", root=tmp_path)["claims"] == []


def test_receipt_roots_at_claim_and_cites_real_graph_rows(tmp_path):
    built = _persist_action_claim(tmp_path)
    receipt = emit_receipt(session_id="s1", root=tmp_path)
    assert receipt["claim_count"] == 1
    claim = receipt["claims"][0]
    assert claim["claim_id"] == built.current_claim_ids[0]
    assert claim["claim_text"] == "I ran `scripts/deploy.sh`"
    assert claim["predicate"] == "action.run"
    assert claim["verdict"] == "CERTIFIED"
    assert claim["trace_bound"] is True
    assert claim["support_path"]

    rows = ledger.read(root=tmp_path)
    for citation in claim["cited_chain_rows"]:
        row = rows[citation["row_index"]]
        assert citation["row_hash"] == row["row_hash"]
        assert citation["id"] in {row.get("node_id"), row.get("edge_id")}


def test_session_id_scopes_actual_claim_nodes(tmp_path):
    _persist_action_claim(tmp_path, session_id="s1", event_id=2)
    _persist_action_claim(tmp_path, session_id="s2", event_id=4)
    receipt = emit_receipt(session_id="s1", root=tmp_path)
    assert receipt["claim_count"] == 1
    assert receipt["claims"][0]["source_event_id"] == 2


def test_tampered_cited_path_keeps_claim_visible_but_demotes_verdict(tmp_path):
    _persist_action_claim(tmp_path)
    chain_file = tmp_path / "chain.jsonl"
    lines = chain_file.read_text().splitlines()
    row0 = json.loads(lines[0])
    row0["canonical_value"] = "TAMPERED"
    lines[0] = json.dumps(row0, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    chain_file.write_text("\n".join(lines) + "\n")

    receipt = emit_receipt(session_id="s1", root=tmp_path)
    assert receipt["verified_through"] == 0
    assert receipt["claim_count"] == 1
    assert receipt["trace_bound_count"] == 0
    assert receipt["claims"][0]["verdict"] == "NOT-EVALUABLE"
    assert receipt["claims"][0]["trace_bound"] is False


def test_exemption_count_reflects_chained_exemption_rows(tmp_path):
    from makoto.record import audit
    audit.append_exemption(
        tmp_path, pattern_id="content.timing_unsafe_compare", kind="makoto-allow",
        file="h.py", line=4, reason="r", snippet="s",
    )
    receipt = emit_receipt(root=tmp_path)
    assert receipt["exemption_count"] == 1
    assert receipt["claim_count"] == 0
