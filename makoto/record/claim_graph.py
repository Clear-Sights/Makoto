"""Persistence and replay for Makoto's append-only claim graph.

The hash chain is authoritative.  SQLite is only a session-scoped query projection and can be
deleted/rebuilt from the verified chain prefix without changing graph identity or verdicts.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from makoto.record import ledger
from makoto.substrate import claim_graph as graph_model
from makoto.substrate.io import decode_history_row


_NODE_KINDS = frozenset({"claim", "deed", "observation", "object"})


@dataclass(frozen=True)
class StopGraph:
    graph: graph_model.ClaimGraph
    current_claim_ids: tuple[str, ...]
    prior_promise_claim_ids: tuple[str, ...]


def ensure_schema(conn) -> None:
    """Create the projection tables on an existing connection, idempotently."""
    from makoto.record.db import _create_claim_graph_tables
    _create_claim_graph_tables(conn)


def _row_index(root: Path, name: str, row_hash: str) -> Optional[int]:
    for index, row in enumerate(ledger.read(name=name, root=root)):
        if row.get("row_hash") == row_hash:
            return index
    return None


def _project_row(conn, row: Mapping, *, row_index=None, row_hash="") -> bool:
    value = graph_model.row_to_graph_value(row)
    if value is None:
        return False
    payload = graph_model.canonical_json(dict(row))
    if isinstance(value, graph_model.Edge):
        conn.execute(
            "INSERT OR IGNORE INTO claim_graph_edges "
            "(session_id, edge_id, edge_kind, source_id, target_id, resolver_id, payload, "
            " chain_row_index, chain_row_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [value.session_id, value.edge_id, value.edge_kind, value.source_id, value.target_id,
             value.resolver_id, payload, row_index, row_hash],
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO claim_graph_nodes "
            "(session_id, node_id, node_kind, source_event_id, actor_id, payload, "
            " chain_row_index, chain_row_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [value.session_id, value.node_id, row.get("kind"),
             str(getattr(value, "source_event_id", "") or ""),
             getattr(value, "actor_id", ""), payload, row_index, row_hash],
        )
    return True


def _already_projected(conn, value) -> bool:
    if isinstance(value, graph_model.Edge):
        row = conn.execute(
            "SELECT 1 FROM claim_graph_edges WHERE session_id = ? AND edge_id = ?",
            [value.session_id, value.edge_id],
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM claim_graph_nodes WHERE session_id = ? AND node_id = ?",
            [value.session_id, value.node_id],
        ).fetchone()
    return row is not None


def persist_value(conn, value, *, root: Optional[Path] = None, name: str = "chain") -> bool:
    """Append one new graph value to the chain, then project it.  Returns True when new."""
    ensure_schema(conn)
    if _already_projected(conn, value):
        return False
    row = (graph_model.edge_to_row(value) if isinstance(value, graph_model.Edge)
           else graph_model.node_to_row(value))
    row_index = None
    row_hash = ""
    if root is not None:
        stored = ledger.append(row, name=name, root=root)
        row_hash = stored.get("row_hash", "")
        row_index = _row_index(root, name, row_hash)
        row = stored
    _project_row(conn, row, row_index=row_index, row_hash=row_hash)
    return True


def persist_graph(conn, graph: graph_model.ClaimGraph, *, root: Optional[Path] = None,
                  name: str = "chain") -> int:
    """Persist every not-yet-projected value in dependency order."""
    count = 0
    for collection in (graph.objects, graph.deeds, graph.observations, graph.claims, graph.edges):
        for value in collection.values():
            count += int(persist_value(conn, value, root=root, name=name))
    return count


def load_projection(conn, session_id: str) -> graph_model.ClaimGraph:
    ensure_schema(conn)
    graph = graph_model.ClaimGraph(session_id=session_id)
    node_rows = conn.execute(
        "SELECT payload, chain_row_index, chain_row_hash FROM claim_graph_nodes "
        "WHERE session_id = ? ORDER BY COALESCE(chain_row_index, -1), rowid",
        [session_id],
    ).fetchall()
    edge_rows = conn.execute(
        "SELECT payload, chain_row_index, chain_row_hash FROM claim_graph_edges "
        "WHERE session_id = ? ORDER BY COALESCE(chain_row_index, -1), rowid",
        [session_id],
    ).fetchall()
    for payload, row_index, row_hash in [*node_rows, *edge_rows]:
        try:
            row = json.loads(payload)
        except (TypeError, ValueError):
            continue
        _add_row_value(graph, row, row_index=row_index, row_hash=row_hash or "")
    return graph


def _add_row_value(graph: graph_model.ClaimGraph, row: Mapping, *, row_index=None,
                   row_hash="") -> None:
    value = graph_model.row_to_graph_value(row)
    if isinstance(value, graph_model.Claim):
        graph.add_claim(value)
        identity = value.node_id
    elif isinstance(value, graph_model.Deed):
        graph.add_deed(value)
        identity = value.node_id
    elif isinstance(value, graph_model.Observation):
        graph.add_observation(value)
        identity = value.node_id
    elif isinstance(value, graph_model.ObjectNode):
        graph.add_object(value)
        identity = value.node_id
    elif isinstance(value, graph_model.Edge):
        graph.add_edge(value)
        identity = value.edge_id
    else:
        return
    if row_index is not None:
        graph.row_refs[identity] = (int(row_index), row_hash)


def graph_from_chain(rows: Sequence[Mapping], *, session_id: str) -> graph_model.ClaimGraph:
    graph = graph_model.ClaimGraph(session_id=session_id)
    for index, row in enumerate(rows or ()):
        if row.get("session_id") != session_id:
            continue
        _add_row_value(graph, row, row_index=index, row_hash=row.get("row_hash", ""))
    return graph


def rebuild_projection(conn, *, root: Optional[Path] = None, name: str = "chain") -> int:
    """Rebuild graph tables from only the chain's verified prefix."""
    ensure_schema(conn)
    broken_at = ledger.verify_chain(name=name, root=root)
    rows = ledger.read(name=name, root=root)
    if broken_at is not None:
        rows = rows[:broken_at]
    conn.execute("DELETE FROM claim_graph_edges")
    conn.execute("DELETE FROM claim_graph_nodes")
    count = 0
    for index, row in enumerate(rows):
        if row.get("kind") not in _NODE_KINDS | {"edge"}:
            continue
        if _project_row(conn, row, row_index=index, row_hash=row.get("row_hash", "")):
            count += 1
    return count


def record_deed(conn, payload: Mapping, *, event_id, session_id: str, cwd: Optional[str],
                root: Optional[Path] = None, name: str = "chain") -> Optional[str]:
    """Persist a settled PostToolUse deed and any observations derived from its result."""
    graph = load_projection(conn, session_id)
    deed = graph_model.ingest_deed_event(
        graph, payload, source_event_id=event_id, cwd=cwd,
    )
    if deed is None:
        return None
    persist_graph(conn, graph, root=root, name=name)
    graph_model.link_claims(graph)
    persist_graph(conn, graph, root=root, name=name)
    return deed.node_id


def _max_history_event_id(history: Sequence) -> int:
    values = []
    for index, row in enumerate(history or ()):
        event_id = graph_model.history_event_id(row, index)
        try:
            values.append(int(event_id))
        except (TypeError, ValueError):
            pass
    return max(values) if values else 0


def _prior_stop_event_id(history: Sequence):
    found = None
    for index, row in enumerate(history or ()):
        payload = decode_history_row(row)
        if isinstance(payload, Mapping) and payload.get("hook_event_name") in {"Stop", "SubagentStop"}:
            found = graph_model.history_event_id(row, index)
    return found


def build_stop_graph(conn, payload: Mapping, history: Sequence, *, event_id=None,
                     root: Optional[Path] = None, fs_exists=None, fs_size=None,
                     name: str = "chain") -> StopGraph:
    """Ingest, persist, observe, link, and return the common graph for one Stop evaluation.

    Claim rows and their host-event/span identity are persisted before any observation or
    adjudication edge is constructed.
    """
    session_id = str(payload.get("session_id", "") or "")
    cwd = payload.get("cwd") or os.getcwd()
    graph = load_projection(conn, session_id)
    graph_model.ingest_history(graph, history, cwd=cwd)
    persist_graph(conn, graph, root=root, name=name)

    if event_id is None:
        event_id = payload.get("source_event_id") or (_max_history_event_id(history) + 1)
    actor_id = graph_model.canonical_actor_id(payload.get("agent_id"))
    current = graph_model.extract_claims(
        graph,
        str(payload.get("last_assistant_message", "") or ""),
        source_event_id=event_id,
        actor_id=actor_id,
        cwd=cwd,
    )
    current_ids = tuple(claim.node_id for claim in current)
    # G01: commit claim + exact span + asserts/targets edges before adjudication begins.
    persist_graph(conn, graph, root=root, name=name)

    graph_model.observe_filesystem_claims(
        graph, current_ids, source_event_id=event_id, fs_exists=fs_exists, fs_size=fs_size,
    )
    graph_model.observe_push_claims(
        graph, current_ids, source_event_id=event_id, cwd=cwd,
    )
    graph_model.link_claims(graph, history=history)
    persist_graph(conn, graph, root=root, name=name)

    prior_event_id = _prior_stop_event_id(history)
    prior_promises = tuple(
        claim.node_id for claim in graph.claims.values()
        if claim.actor_id == actor_id and claim.tense == "future"
        and claim.predicate.startswith("promise.")
        and prior_event_id is not None and str(claim.source_event_id) == str(prior_event_id)
    )
    return StopGraph(
        graph=graph,
        current_claim_ids=current_ids,
        prior_promise_claim_ids=prior_promises,
    )
