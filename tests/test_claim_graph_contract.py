"""Executable G01-G12 floor for the persisted claim graph.

The integration cases enter through ``python -m makoto._dispatch`` and are inspected through the
production receipt.  The mutation/rebuild cases use the same persisted model directly so each
required edge and chain boundary can be removed deterministically.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from makoto.record import claim_graph as graph_store
from makoto.record import ledger
from makoto.record.db import _connect, init_db
from makoto.record.receipt import emit_receipt
from makoto.substrate.claim_graph import ObjectNode, Verdict, build_ephemeral_graph


def _state(tmp_path: Path):
    root = tmp_path / "state"
    citations = tmp_path / "CITATIONS.md"
    citations.write_text("", encoding="utf-8")
    init_db(root, citations)
    return root


def _dispatch(root: Path, payload: dict) -> str:
    env = os.environ.copy()
    env["MAKOTO_STATE_DIR"] = str(root)
    env["MAKOTO_MODE"] = "strict"
    proc = subprocess.run(
        [sys.executable, "-m", "makoto._dispatch"],
        input=json.dumps(payload).encode(), capture_output=True, env=env,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    return proc.stdout.decode()


def _post(*, session: str, cwd: Path, tool: str, tool_input: dict,
          response: dict, agent_id=None) -> dict:
    payload = {
        "hook_event_name": "PostToolUse", "session_id": session, "cwd": str(cwd),
        "tool_name": tool, "tool_input": tool_input, "tool_response": response,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return payload


def _stop(*, session: str, cwd: Path, text: str, agent_id=None) -> dict:
    payload = {
        "hook_event_name": "Stop", "session_id": session, "cwd": str(cwd),
        "last_assistant_message": text,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return payload


def _receipt_claim(root: Path, session: str, *, predicate=None):
    claims = emit_receipt(session_id=session, root=root)["claims"]
    if predicate is not None:
        claims = [claim for claim in claims if claim["predicate"] == predicate]
    assert claims
    return claims[-1]


def _edge_rows(root: Path, session: str) -> list[dict]:
    return [row for row in ledger.read(root=root)
            if row.get("session_id") == session and row.get("kind") == "edge"]


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Makoto Contract",
        "GIT_AUTHOR_EMAIL": "makoto@example.invalid",
        "GIT_COMMITTER_NAME": "Makoto Contract",
        "GIT_COMMITTER_EMAIL": "makoto@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True, env=env,
    ).stdout.strip()


def _repo_with_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def test_g01_claim_persists_exact_host_event_and_span_before_adjudication(tmp_path):
    root = _state(tmp_path)
    session = "g01"
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Bash",
        tool_input={"command": "scripts/deploy.sh"}, response={"exitCode": 0},
    ))
    text = "Summary: I ran `scripts/deploy.sh`."
    assert _dispatch(root, _stop(session=session, cwd=tmp_path, text=text)) == ""

    conn = sqlite3.connect(root / "makoto.record.db")
    stop_event_id, = conn.execute(
        "SELECT id FROM events WHERE session_id=? AND event_type='Stop'", [session],
    ).fetchone()
    conn.close()
    claim = _receipt_claim(root, session, predicate="action.run")
    assert claim["source_event_id"] == stop_event_id
    assert text[claim["span"]["start"]:claim["span"]["end"]] == claim["claim_text"]
    assert claim["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    rows = ledger.read(root=root)
    claim_index = next(i for i, row in enumerate(rows)
                       if row.get("node_id") == claim["claim_id"])
    support_index = next(i for i, row in enumerate(rows)
                         if row.get("kind") == "edge" and row.get("edge_kind") == "supports"
                         and row.get("target_id") == claim["claim_id"])
    assert claim_index < support_index


def test_g02_evidence_deed_is_a_distinct_settled_host_event_and_cannot_self_support(tmp_path):
    root = _state(tmp_path)
    session = "g02"
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Bash",
        tool_input={"command": "scripts/deploy.sh"}, response={"exitCode": 0},
    ))
    _dispatch(root, _stop(
        session=session, cwd=tmp_path, text="I ran `scripts/deploy.sh`.",
    ))
    receipt = _receipt_claim(root, session, predicate="action.run")
    rows = ledger.read(root=root)
    cited = {citation["id"] for citation in receipt["support_path"]}
    deeds = [row for row in rows if row.get("kind") == "deed" and row.get("node_id") in cited]
    assert len(deeds) == 1
    deed = deeds[0]
    assert deed["source_event_id"] != receipt["source_event_id"]
    assert deed["input_sha256"] and deed["response_sha256"]
    assert any(row.get("edge_kind") == "performed" and row.get("target_id") == deed["node_id"]
               and row.get("edge_id") in cited for row in rows)
    assert all(row.get("source_id") != receipt["claim_id"]
               for row in rows if row.get("edge_kind") == "supports")


def test_g03_unrelated_read_cannot_support_claimed_deploy_command(tmp_path):
    root = _state(tmp_path)
    session = "g03"
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Read",
        tool_input={"file_path": "README.md"}, response={"content": "read"},
    ))
    out = _dispatch(root, _stop(
        session=session, cwd=tmp_path, text="I ran `scripts/deploy.sh`.",
    ))
    assert json.loads(out)["decision"] == "block"
    assert _receipt_claim(root, session, predicate="action.run")["verdict"] == "NOT-EVALUABLE"


def test_g04_unrelated_bash_cannot_discharge_targeted_deploy_promise(tmp_path):
    root = _state(tmp_path)
    session = "g04"
    _dispatch(root, _stop(
        session=session, cwd=tmp_path,
        text="I'll deploy `release-2026-08` to production.",
    ))
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Bash",
        tool_input={"command": "printf unrelated"},
        response={"stdout": "unrelated", "exitCode": 0},
    ))
    out = _dispatch(root, _stop(session=session, cwd=tmp_path, text="No further claim."))
    assert json.loads(out)["decision"] == "block"
    claim = _receipt_claim(root, session, predicate="promise.deploy")
    assert claim["target"]["canonical_value"] == "release-2026-08"
    assert claim["verdict"] == "NOT-EVALUABLE"


def test_g05_other_repository_merge_cannot_support_named_makoto_pr(tmp_path):
    root = _state(tmp_path)
    session = "g05"
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="merge_pull_request",
        tool_input={"owner": "other", "repo": "other", "pullNumber": 7},
        response={"merged": True, "sha": "abc123"},
    ))
    out = _dispatch(root, _stop(
        session=session, cwd=tmp_path,
        text="I merged Clear-Sights/makoto PR #999.",
    ))
    assert json.loads(out)["decision"] == "block"
    claim = _receipt_claim(root, session, predicate="remote.merge")
    assert claim["target"]["canonical_value"] == "clear-sights/makoto#999"
    assert claim["verdict"] == "NOT-EVALUABLE"


def test_g06_named_failure_is_target_local_and_later_exact_pass_supersedes(tmp_path):
    root = _state(tmp_path)
    session = "g06"
    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Bash",
        tool_input={"command": "pytest tests/test_graph.py -q"},
        response={
            "stdout": "FAILED tests/test_graph.py::test_alpha - AssertionError\n1 failed",
            "exitCode": 1,
        },
    ))
    _dispatch(root, _stop(
        session=session, cwd=tmp_path,
        text="test_alpha passes now; test_beta passes now.",
    ))
    first = emit_receipt(session_id=session, root=root)["claims"]
    by_target = {claim["target"]["canonical_value"]: claim for claim in first
                 if claim["predicate"] == "test.pass.named"}
    assert by_target["test_alpha"]["verdict"] == "CONTRADICTED"
    assert by_target["test_beta"]["verdict"] == "NOT-EVALUABLE"

    _dispatch(root, _post(
        session=session, cwd=tmp_path, tool="Bash",
        tool_input={"command": "pytest tests/test_graph.py::test_alpha -q"},
        response={"stdout": "PASSED tests/test_graph.py::test_alpha\n1 passed", "exitCode": 0},
    ))
    second = emit_receipt(session_id=session, root=root)["claims"]
    by_target = {claim["target"]["canonical_value"]: claim for claim in second
                 if claim["predicate"] == "test.pass.named"}
    assert by_target["test_alpha"]["verdict"] == "CERTIFIED"
    assert by_target["test_beta"]["verdict"] == "NOT-EVALUABLE"
    assert any(row.get("edge_kind") == "supersedes" for row in _edge_rows(root, session))
    conn = _connect(root / "makoto.record.db")
    graph = graph_store.load_projection(conn, session)
    conn.close()
    alpha_id = next(claim.node_id for claim in graph.claims.values()
                    if claim.target_value == "test_alpha")
    alpha_path = graph.adjudicate(alpha_id)
    derived_id = next(edge_id for edge_id in alpha_path.path_edge_ids
                      if graph.edges[edge_id].edge_kind == "derived-from")
    del graph.edges[derived_id]
    assert graph.adjudicate(alpha_id).verdict is Verdict.NOT_EVALUABLE


def test_g07_push_requires_same_repository_remote_ref_and_tip_observation(tmp_path):
    repo = _repo_with_origin(tmp_path)
    root = _state(tmp_path)
    assert _dispatch(root, _stop(
        session="g07-match", cwd=repo, text="I've pushed it to main.",
    )) == ""
    matched = _receipt_claim(root, "g07-match", predicate="remote.push")
    assert matched["verdict"] == "CERTIFIED"
    assert matched["resolver"]["id"] == "git-remote-tip"
    assert "refs/heads/main" in matched["target"]["canonical_value"]

    (repo / "seed.txt").write_text("local advance\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "local-only")
    out = _dispatch(root, _stop(
        session="g07-mismatch", cwd=repo, text="I've pushed it to main.",
    ))
    assert json.loads(out)["decision"] == "block"
    mismatched = _receipt_claim(root, "g07-mismatch", predicate="remote.push")
    assert mismatched["verdict"] == "CONTRADICTED"
    assert mismatched["target"]["canonical_value"] == matched["target"]["canonical_value"]


def test_g08_cross_actor_support_requires_exact_delegation_and_target_edges(tmp_path):
    root = _state(tmp_path)
    target = "Clear-Sights/makoto PR #42"
    _dispatch(root, _post(
        session="g08-ok", cwd=tmp_path, tool="Agent",
        tool_input={"prompt": f"Merge {target}"},
        response={"agent_id": "child-1", "status": "completed"},
    ))
    _dispatch(root, _post(
        session="g08-ok", cwd=tmp_path, tool="merge_pull_request", agent_id="child-1",
        tool_input={"owner": "Clear-Sights", "repo": "makoto", "pullNumber": 42},
        response={"merged": True, "sha": "abc"},
    ))
    assert _dispatch(root, _stop(
        session="g08-ok", cwd=tmp_path, text=f"I merged {target}.",
    )) == ""
    supported = _receipt_claim(root, "g08-ok", predicate="remote.merge")
    assert supported["verdict"] == "CERTIFIED"
    assert any(row.get("edge_kind") == "delegated-to"
               and row.get("object_id") == supported["target"]["object_id"]
               for row in _edge_rows(root, "g08-ok"))
    conn = _connect(root / "makoto.record.db")
    delegated_graph = graph_store.load_projection(conn, "g08-ok")
    conn.close()
    delegation = next(edge_id for edge_id, edge in delegated_graph.edges.items()
                      if edge.edge_kind == "delegated-to")
    del delegated_graph.edges[delegation]
    assert delegated_graph.adjudicate(supported["claim_id"]).verdict is Verdict.NOT_EVALUABLE

    _dispatch(root, _post(
        session="g08-no-delegation", cwd=tmp_path, tool="merge_pull_request",
        agent_id="child-2",
        tool_input={"owner": "Clear-Sights", "repo": "makoto", "pullNumber": 42},
        response={"merged": True, "sha": "def"},
    ))
    out = _dispatch(root, _stop(
        session="g08-no-delegation", cwd=tmp_path, text=f"I merged {target}.",
    ))
    assert json.loads(out)["decision"] == "block"
    assert _receipt_claim(
        root, "g08-no-delegation", predicate="remote.merge",
    )["verdict"] == "NOT-EVALUABLE"


def test_g09_receipt_roots_at_claim_and_cites_complete_path_not_bare_deed(tmp_path):
    root = _state(tmp_path)
    ledger.append({"kind": "testrun", "key": "bare", "session_id": "g09"}, root=root)
    assert emit_receipt(session_id="g09", root=root)["claim_count"] == 0
    _dispatch(root, _post(
        session="g09", cwd=tmp_path, tool="Bash",
        tool_input={"command": "scripts/deploy.sh"}, response={"exitCode": 0},
    ))
    _dispatch(root, _stop(
        session="g09", cwd=tmp_path, text="I ran `scripts/deploy.sh`.",
    ))
    claim = _receipt_claim(root, "g09", predicate="action.run")
    assert "claim_kind" not in claim
    assert claim["claim_id"] and claim["support_path"] and claim["trace_bound"]
    cited = {item["id"] for item in claim["support_path"]}
    cited_edges = {row["edge_kind"] for row in _edge_rows(root, "g09")
                   if row["edge_id"] in cited}
    assert {"asserts", "performed", "targets", "supports"} <= cited_edges


def test_g10_composite_session_identity_survives_verified_chain_rebuild(tmp_path):
    root = _state(tmp_path)
    conn = _connect(root / "makoto.record.db")
    for offset, session in ((0, "g10-a"), (10, "g10-b")):
        history = [(1 + offset, "t", "PostToolUse", str(tmp_path), json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "scripts/deploy.sh"},
            "tool_response": {"exitCode": 0},
        }))]
        graph_store.build_stop_graph(conn, {
            "hook_event_name": "Stop", "session_id": session, "cwd": str(tmp_path),
            "last_assistant_message": "I ran `scripts/deploy.sh`.",
        }, history, event_id=2 + offset, root=root)
    assert conn.execute(
        "SELECT COUNT(*) FROM claim_graph_nodes WHERE node_kind='claim'",
    ).fetchone()[0] == 2
    conn.execute("DELETE FROM claim_graph_edges")
    conn.execute("DELETE FROM claim_graph_nodes")
    assert graph_store.rebuild_projection(conn, root=root) > 0
    assert len(graph_store.load_projection(conn, "g10-a").claims) == 1
    assert len(graph_store.load_projection(conn, "g10-b").claims) == 1
    conn.close()


def test_g11_every_required_edge_is_live_and_target_swaps_never_support(tmp_path):
    history = [(1, "t", "PostToolUse", str(tmp_path), json.dumps({
        "hook_event_name": "PostToolUse", "tool_name": "Bash",
        "tool_input": {"command": "scripts/deploy.sh"},
        "tool_response": {"exitCode": 0},
    }))]
    graph, claim_ids = build_ephemeral_graph(
        "I ran `scripts/deploy.sh`.", history=history, cwd=str(tmp_path),
    )
    claim_id = claim_ids[0]
    adjudication = graph.adjudicate(claim_id)
    assert adjudication.verdict is Verdict.CERTIFIED
    assert len(adjudication.path_edge_ids) >= 4
    for edge_id in adjudication.path_edge_ids:
        cut = copy.deepcopy(graph)
        del cut.edges[edge_id]
        assert cut.adjudicate(claim_id).verdict is Verdict.NOT_EVALUABLE, edge_id

    swapped = copy.deepcopy(graph)
    deed_id = adjudication.evidence_id
    deed_target = next(edge for edge in swapped.edges.values()
                       if edge.edge_kind == "targets" and edge.source_id == deed_id
                       and edge.target_id == swapped.claims[claim_id].target_id)
    other = ObjectNode.make(swapped.session_id, "executable", "scripts/other.sh")
    swapped.add_object(other)
    swapped.edges[deed_target.edge_id] = replace(
        deed_target, target_id=other.node_id, object_id=other.node_id,
    )
    assert swapped.adjudicate(claim_id).verdict is Verdict.NOT_EVALUABLE


def test_g12_corrupt_cited_row_demotes_at_exact_chain_break(tmp_path):
    root = _state(tmp_path)
    conn = _connect(root / "makoto.record.db")
    history = [(1, "t", "PostToolUse", str(tmp_path), json.dumps({
        "hook_event_name": "PostToolUse", "tool_name": "Bash",
        "tool_input": {"command": "scripts/deploy.sh"},
        "tool_response": {"exitCode": 0},
    }))]
    graph_store.build_stop_graph(conn, {
        "hook_event_name": "Stop", "session_id": "g12", "cwd": str(tmp_path),
        "last_assistant_message": "I ran `scripts/deploy.sh`.",
    }, history, event_id=2, root=root)
    conn.close()
    before = _receipt_claim(root, "g12", predicate="action.run")
    assert before["verdict"] == "CERTIFIED" and before["trace_bound"]

    chain_path = root / "chain.jsonl"
    lines = chain_path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    broken_at = next(i for i, row in enumerate(rows)
                     if row.get("edge_kind") == "supports"
                     and row.get("target_id") == before["claim_id"])
    rows[broken_at]["reason"] = "TAMPERED"
    lines[broken_at] = json.dumps(
        rows[broken_at], sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    chain_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    after_receipt = emit_receipt(session_id="g12", root=root)
    assert after_receipt["verified_through"] == broken_at
    assert after_receipt["claim_count"] == 1
    assert after_receipt["trace_bound_count"] == 0
    after = after_receipt["claims"][0]
    assert after["claim_id"] == before["claim_id"]
    assert after["verdict"] == "NOT-EVALUABLE"
    assert after["trace_bound"] is False
