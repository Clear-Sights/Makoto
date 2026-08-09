"""Persistence invariants for the claim graph's chain-backed SQLite projection."""
from __future__ import annotations

import json

from makoto.record import claim_graph as store
from makoto.record import ledger
from makoto.record.db import _connect, init_db
from makoto.substrate.claim_graph import Verdict


def _state(tmp_path):
    root = tmp_path / "state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("", encoding="utf-8")
    init_db(root, citations)
    return root, _connect(root / "makoto.record.db")


def _post_row(event_id, cwd, command, *, session_id="s", agent_id=None):
    payload = {
        "hook_event_name": "PostToolUse",
        "session_id": session_id,
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"exitCode": 0},
    }
    if agent_id:
        payload["agent_id"] = agent_id
    return (event_id, "t", "PostToolUse", str(cwd), json.dumps(payload))


def test_claim_is_chained_before_adjudication_with_exact_stop_span(tmp_path):
    root, conn = _state(tmp_path)
    history = [_post_row(10, tmp_path, "./scripts/deploy.sh")]
    stop = store.build_stop_graph(conn, {
        "hook_event_name": "Stop",
        "session_id": "s",
        "cwd": str(tmp_path),
        "last_assistant_message": "Summary: I ran `scripts/deploy.sh`.",
    }, history, event_id=11, root=root)

    claim = stop.graph.claims[stop.current_claim_ids[0]]
    assert claim.source_event_id == 11
    assert claim.span_text == "I ran `scripts/deploy.sh`"
    assert claim.text_sha256
    assert stop.graph.adjudicate(claim.node_id).verdict is Verdict.CERTIFIED

    rows = ledger.read(root=root)
    claim_index = next(i for i, row in enumerate(rows) if row.get("node_id") == claim.node_id)
    support_index = next(i for i, row in enumerate(rows)
                         if row.get("kind") == "edge" and row.get("edge_kind") == "supports")
    assert claim_index < support_index


def test_deed_identity_cites_a_distinct_settled_posttool_event(tmp_path):
    root, conn = _state(tmp_path)
    history = [_post_row(20, tmp_path, "./scripts/deploy.sh")]
    stop = store.build_stop_graph(conn, {
        "hook_event_name": "Stop", "session_id": "s", "cwd": str(tmp_path),
        "last_assistant_message": "I ran `scripts/deploy.sh`.",
    }, history, event_id=21, root=root)
    adjudication = stop.graph.adjudicate(stop.current_claim_ids[0])
    deed = stop.graph.deeds[adjudication.evidence_id]
    assert deed.source_event_id == 20
    assert deed.source_event_id != stop.graph.claims[stop.current_claim_ids[0]].source_event_id
    assert deed.input_sha256 and deed.response_sha256


def test_projection_rebuild_retains_same_target_in_two_sessions(tmp_path):
    root, conn = _state(tmp_path)
    for offset, session_id in ((0, "first"), (10, "second")):
        history = [_post_row(1 + offset, tmp_path, "./scripts/deploy.sh", session_id=session_id)]
        store.build_stop_graph(conn, {
            "hook_event_name": "Stop", "session_id": session_id, "cwd": str(tmp_path),
            "last_assistant_message": "I ran `scripts/deploy.sh`.",
        }, history, event_id=2 + offset, root=root)

    assert conn.execute(
        "SELECT COUNT(*) FROM claim_graph_nodes WHERE node_kind = 'claim'"
    ).fetchone()[0] == 2
    conn.execute("DELETE FROM claim_graph_edges")
    conn.execute("DELETE FROM claim_graph_nodes")
    replayed = store.rebuild_projection(conn, root=root)
    assert replayed > 0
    assert len(store.load_projection(conn, "first").claims) == 1
    assert len(store.load_projection(conn, "second").claims) == 1


def test_rebuild_stops_at_first_broken_chain_row(tmp_path):
    root, conn = _state(tmp_path)
    store.build_stop_graph(conn, {
        "hook_event_name": "Stop", "session_id": "s", "cwd": str(tmp_path),
        "last_assistant_message": "I ran `scripts/deploy.sh`.",
    }, [], event_id=1, root=root)
    chain = root / "chain.jsonl"
    rows = chain.read_text(encoding="utf-8").splitlines()
    changed = json.loads(rows[0])
    changed["canonical_value"] = "tampered"
    rows[0] = json.dumps(changed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    chain.write_text("\n".join(rows) + "\n", encoding="utf-8")

    assert ledger.verify_chain(root=root) == 0
    assert store.rebuild_projection(conn, root=root) == 0
    assert store.load_projection(conn, "s").claims == {}
