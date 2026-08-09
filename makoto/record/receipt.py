"""Claim-rooted receipt view over the tamper-evident graph chain.

A receipt never infers claims from deed kinds.  It starts at persisted ``claim`` nodes and cites
the complete semantic path used by the deterministic adjudicator.  A broken cited row keeps the
claim visible but demotes its receipt verdict to NOT-EVALUABLE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from makoto.record import claim_graph as graph_store
from makoto.record import ledger
from makoto.substrate.claim_graph import Verdict


_EXEMPTION_KIND = "exemption"


def _session_matches(row: dict, session_id: Optional[str]) -> bool:
    return session_id is None or row.get("session_id") == session_id


def _trace_bound(row_index: int, verified_through: Optional[int]) -> bool:
    return verified_through is None or row_index < verified_through


def _citation(graph, identity: str, *, kind: str) -> Optional[dict]:
    ref = graph.row_refs.get(identity)
    if ref is None:
        return None
    row_index, row_hash = ref
    return {
        "kind": kind,
        "id": identity,
        "row_index": row_index,
        "row_hash": row_hash,
    }


def _claim_receipt(graph, claim, verified_through: Optional[int]) -> dict:
    adjudication = graph.adjudicate(claim.node_id)
    target = graph.objects.get(claim.target_id)
    identity_kinds = {claim.node_id: "claim"}
    identity_kinds.update({node_id: (
        "deed" if node_id in graph.deeds else
        "observation" if node_id in graph.observations else
        "object" if node_id in graph.objects else "node"
    ) for node_id in adjudication.path_node_ids})
    identity_kinds.update({edge_id: "edge" for edge_id in adjudication.path_edge_ids})

    # The host assertion and claim-target edges are provenance requirements even when no
    # evidence edge exists, so every receipt cites them explicitly.
    for edge in graph.edges.values():
        if edge.edge_kind == "asserts" and edge.target_id == claim.node_id:
            identity_kinds[edge.edge_id] = "edge"
        if edge.edge_kind == "targets" and edge.source_id == claim.node_id:
            identity_kinds[edge.edge_id] = "edge"
            identity_kinds[edge.target_id] = "object"

    citations = []
    for identity, kind in identity_kinds.items():
        cited = _citation(graph, identity, kind=kind)
        if cited is not None:
            citations.append(cited)
    citations.sort(key=lambda item: (item["row_index"], item["id"]))
    trace_bound = bool(citations) and all(
        _trace_bound(item["row_index"], verified_through) for item in citations
    )

    effective_verdict = adjudication.verdict
    if effective_verdict in {Verdict.CERTIFIED, Verdict.CONTRADICTED} and not trace_bound:
        effective_verdict = Verdict.NOT_EVALUABLE
    support_path = citations if effective_verdict is Verdict.CERTIFIED else []
    contradiction_path = citations if effective_verdict is Verdict.CONTRADICTED else []
    return {
        "claim_id": claim.node_id,
        "source_event_id": claim.source_event_id,
        "actor": claim.actor,
        "actor_id": claim.actor_id,
        "text_sha256": claim.text_sha256,
        "claim_text": claim.span_text,
        "span": {"start": claim.span_start, "end": claim.span_end},
        "parser_version": claim.parser_version,
        "predicate": claim.predicate,
        "target": {
            "object_id": claim.target_id,
            "type": claim.target_type,
            "canonical_value": claim.target_value,
            "display_value": target.display_value if target is not None else claim.target_value,
        },
        "tense": claim.tense,
        "polarity": claim.polarity,
        "verdict": effective_verdict.value,
        "resolver": ({
            "id": adjudication.resolver_id,
            "version": adjudication.resolver_version,
        } if adjudication.resolver_id and effective_verdict is not Verdict.NOT_EVALUABLE else None),
        "support_path": support_path,
        "contradiction_path": contradiction_path,
        "cited_chain_rows": citations,
        "trace_bound": trace_bound,
    }


def emit_receipt(*, session_id: Optional[str] = None, name: str = "chain",
                 root: Optional[Path] = None) -> dict:
    """Compute a claim-rooted receipt, optionally scoped to one session."""
    rows = ledger.read(name=name, root=root)
    verified_through = ledger.verify_chain(name=name, root=root)
    session_ids = sorted({
        str(row.get("session_id", "")) for row in rows
        if row.get("kind") == "claim" and row.get("graph_schema_version")
        and _session_matches(row, session_id)
    })
    claims = []
    for sid in session_ids:
        graph = graph_store.graph_from_chain(rows, session_id=sid)
        ordered = sorted(
            graph.claims.values(),
            key=lambda claim: graph.row_refs.get(claim.node_id, (10**18, ""))[0],
        )
        claims.extend(_claim_receipt(graph, claim, verified_through) for claim in ordered)

    exemption_count = sum(
        1 for index, row in enumerate(rows)
        if row.get("kind") == _EXEMPTION_KIND and _session_matches(row, session_id)
        and _trace_bound(index, verified_through)
    )
    return {
        "session_id": session_id,
        "chain_name": name,
        "verified_through": verified_through,
        "claims": claims,
        "claim_count": len(claims),
        "trace_bound_count": sum(1 for claim in claims if claim["trace_bound"]),
        "exemption_count": exemption_count,
    }
