"""Typed claim-graph primitives and deterministic coreference resolvers.

The graph is the semantic layer between an assistant-authored claim and host-captured
evidence.  Proximity and broad event shape never create support: a resolver may link evidence
to a claim only when both target the same canonical object and the resolver is registered for
that claim predicate.

This module is deliberately storage-free.  ``makoto.record.claim_graph`` projects these values
to SQLite and the existing tamper-evident chain; Stop gates consume the same in-memory graph.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from makoto.core._shell import (
    _command_pushes_git,
    _command_runs_tests,
    _effective_argv,
    _shell_segments,
)
from makoto.core.lexicons import (
    _ADV_FORWARD_RX,
    _BE_AUX_RX,
    _CLAUSE_BREAK_RX,
    _FORWARD_FRAME_RX,
    _GREEN_CLAIM_RX,
    _GREEN_UNIVERSAL_PREMOD,
    _NEGATION_RX,
    _NEG_FRAME_RX,
    _PROCESS_LIFECYCLE_CMD_RX,
    _PROCESS_START_VERB_RX,
    _PRODUCE_VERB_RX,
    _RUNNING_CLAIM_RX,
    _RUN_INTENT_CLAIM_RX,
    _RUN_INTENT_IDIOM_VETO_RX,
    _SENTENCE_SPLIT_RX,
    _SHIPPED_ACTION_CLAIM_RX,
    _SHIPPED_STATE_CLAIM_RX,
    _TEETH_FRAME_RX,
)
from makoto.substrate._primitives import detect_locations, normalize_path
from makoto.substrate.claims import _code_spans
from makoto.substrate.io import bash_output_text, decode_history_row, is_failing_testrun


GRAPH_SCHEMA_VERSION = "1"
PARSER_VERSION = "claim-parser-v1"
RESOLVER_VERSION = "1"


class Verdict(str, Enum):
    CERTIFIED = "CERTIFIED"
    CONTRADICTED = "CONTRADICTED"
    NOT_EVALUABLE = "NOT-EVALUABLE"


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts) -> str:
    body = canonical_json(parts)
    return f"{prefix}:{sha256_text(body)}"


def canonical_actor_id(agent_id=None) -> str:
    if isinstance(agent_id, str) and agent_id.strip():
        return f"agent:{agent_id.strip()}"
    return "agent:main"


def actor_object_id(actor_id: str) -> str:
    return stable_id("object", "actor", actor_id)


def _event_order(value) -> tuple[int, str]:
    if isinstance(value, int):
        return (value, "")
    try:
        return (int(value), "")
    except (TypeError, ValueError):
        return (-1, str(value))


@dataclass(frozen=True)
class ObjectNode:
    node_id: str
    session_id: str
    object_type: str
    canonical_value: str
    display_value: str

    @classmethod
    def make(cls, session_id: str, object_type: str, canonical_value: str,
             display_value: Optional[str] = None) -> "ObjectNode":
        value = str(canonical_value or "")
        return cls(
            node_id=stable_id("object", object_type, value),
            session_id=session_id,
            object_type=object_type,
            canonical_value=value,
            display_value=str(display_value if display_value is not None else value),
        )


@dataclass(frozen=True)
class Claim:
    node_id: str
    session_id: str
    source_event_id: object
    actor: str
    actor_id: str
    text_sha256: str
    span_start: int
    span_end: int
    span_text: str
    parser_version: str
    predicate: str
    target_id: str
    target_type: str
    target_value: str
    tense: str
    polarity: str

    @classmethod
    def make(cls, *, session_id: str, source_event_id, actor_id: str, full_text: str,
             span_start: int, span_end: int, predicate: str, target: ObjectNode,
             tense: str = "past", polarity: str = "positive") -> "Claim":
        digest = sha256_text(full_text)
        node_id = stable_id(
            "claim", session_id, source_event_id, span_start, span_end, PARSER_VERSION, digest,
        )
        return cls(
            node_id=node_id,
            session_id=session_id,
            source_event_id=source_event_id,
            actor="assistant",
            actor_id=actor_id,
            text_sha256=digest,
            span_start=span_start,
            span_end=span_end,
            span_text=full_text[span_start:span_end],
            parser_version=PARSER_VERSION,
            predicate=predicate,
            target_id=target.node_id,
            target_type=target.object_type,
            target_value=target.canonical_value,
            tense=tense,
            polarity=polarity,
        )


@dataclass(frozen=True)
class Deed:
    node_id: str
    session_id: str
    source_event_id: object
    actor: str
    actor_id: str
    tool: str
    input_sha256: str
    response_sha256: str
    status: str
    actions: tuple[str, ...]
    canonical_input: str

    @classmethod
    def make(cls, *, session_id: str, source_event_id, actor_id: str, tool: str,
             tool_input: Mapping, tool_response, status: str,
             actions: Iterable[str]) -> "Deed":
        input_text = canonical_json(tool_input if isinstance(tool_input, Mapping) else {})
        response_text = canonical_json(tool_response)
        input_digest = sha256_text(input_text)
        response_digest = sha256_text(response_text)
        return cls(
            node_id=stable_id(
                "deed", session_id, source_event_id, tool, input_digest, response_digest,
            ),
            session_id=session_id,
            source_event_id=source_event_id,
            actor="assistant",
            actor_id=actor_id,
            tool=tool,
            input_sha256=input_digest,
            response_sha256=response_digest,
            status=status,
            actions=tuple(sorted(set(actions))),
            canonical_input=input_text,
        )


@dataclass(frozen=True)
class Observation:
    node_id: str
    session_id: str
    source_event_id: object
    actor_id: str
    predicate: str
    target_id: str
    status: str
    resolver_id: str
    resolver_version: str
    source: str
    value: str = ""

    @classmethod
    def make(cls, *, session_id: str, source_event_id, actor_id: str, predicate: str,
             target: ObjectNode, status: str, resolver_id: str, source: str,
             value: str = "") -> "Observation":
        return cls(
            node_id=stable_id(
                "observation", session_id, source_event_id, predicate, target.node_id,
                status, resolver_id, value,
            ),
            session_id=session_id,
            source_event_id=source_event_id,
            actor_id=actor_id,
            predicate=predicate,
            target_id=target.node_id,
            status=status,
            resolver_id=resolver_id,
            resolver_version=RESOLVER_VERSION,
            source=source,
            value=value,
        )


@dataclass(frozen=True)
class Edge:
    edge_id: str
    session_id: str
    edge_kind: str
    source_id: str
    target_id: str
    resolver_id: str = ""
    resolver_version: str = ""
    reason: str = ""
    object_id: str = ""
    source_event_id: object = None

    @classmethod
    def make(cls, *, session_id: str, edge_kind: str, source_id: str, target_id: str,
             resolver_id: str = "", resolver_version: str = "", reason: str = "",
             object_id: str = "", source_event_id=None) -> "Edge":
        return cls(
            edge_id=stable_id(
                "edge", session_id, edge_kind, source_id, target_id, resolver_id,
                resolver_version, object_id,
            ),
            session_id=session_id,
            edge_kind=edge_kind,
            source_id=source_id,
            target_id=target_id,
            resolver_id=resolver_id,
            resolver_version=resolver_version,
            reason=reason,
            object_id=object_id,
            source_event_id=source_event_id,
        )


@dataclass(frozen=True)
class Adjudication:
    claim_id: str
    verdict: Verdict
    evidence_id: str = ""
    resolver_id: str = ""
    resolver_version: str = ""
    reason: str = ""
    path_node_ids: tuple[str, ...] = ()
    path_edge_ids: tuple[str, ...] = ()


_RESOLVER_PREDICATES = {
    "exact-command": frozenset({
        "action.run", "action.execute", "action.install", "action.fetch", "action.clone",
        "action.pull", "action.launch", "action.deploy",
    }),
    "run-promise": frozenset({
        "promise.run", "promise.test", "promise.deploy", "promise.launch",
        "promise.restart",
    }),
    "service-endpoint": frozenset({"service.running"}),
    "github-merge": frozenset({"remote.merge"}),
    "git-remote-tip": frozenset({"remote.push"}),
    "named-test": frozenset({"test.pass.named"}),
    "suite-test": frozenset({"test.pass.suite"}),
    "filesystem-path": frozenset({"file.produced"}),
}


@dataclass
class ClaimGraph:
    session_id: str
    claims: dict[str, Claim] = field(default_factory=dict)
    deeds: dict[str, Deed] = field(default_factory=dict)
    observations: dict[str, Observation] = field(default_factory=dict)
    objects: dict[str, ObjectNode] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    row_refs: dict[str, tuple[int, str]] = field(default_factory=dict)

    def add_object(self, obj: ObjectNode) -> ObjectNode:
        self.objects.setdefault(obj.node_id, obj)
        return obj

    def add_claim(self, claim: Claim) -> Claim:
        self.claims.setdefault(claim.node_id, claim)
        return claim

    def add_deed(self, deed: Deed) -> Deed:
        self.deeds.setdefault(deed.node_id, deed)
        return deed

    def add_observation(self, observation: Observation) -> Observation:
        self.observations.setdefault(observation.node_id, observation)
        return observation

    def add_edge(self, edge: Edge) -> Edge:
        self.edges.setdefault(edge.edge_id, edge)
        return edge

    def target_edges(self, source_id: str) -> list[Edge]:
        return [
            edge for edge in self.edges.values()
            if edge.edge_kind == "targets" and edge.source_id == source_id
        ]

    def semantic_edges(self, claim_id: str) -> list[Edge]:
        return [
            edge for edge in self.edges.values()
            if edge.edge_kind in {"supports", "contradicts"} and edge.target_id == claim_id
        ]

    def _node(self, node_id: str):
        return self.claims.get(node_id) or self.deeds.get(node_id) \
            or self.observations.get(node_id) or self.objects.get(node_id)

    def _is_superseded(self, evidence_id: str) -> bool:
        return any(
            edge.edge_kind == "supersedes" and edge.target_id == evidence_id
            for edge in self.edges.values()
        )

    def _performed_edge(self, deed: Deed) -> Optional[Edge]:
        actor_id = actor_object_id(deed.actor_id)
        return next((
            edge for edge in self.edges.values()
            if edge.edge_kind == "performed" and edge.source_id == actor_id
            and edge.target_id == deed.node_id
        ), None)

    def _delegation_path(self, claim: Claim, evidence, object_id: str) -> tuple[list[str], list[str]]:
        evidence_actor = getattr(evidence, "actor_id", "")
        if not evidence_actor or evidence_actor == claim.actor_id:
            return ([], [])
        claim_actor = actor_object_id(claim.actor_id)
        deed_actor = actor_object_id(evidence_actor)
        delegation = next((
            edge for edge in self.edges.values()
            if edge.edge_kind == "delegated-to" and edge.source_id == claim_actor
            and edge.target_id == deed_actor and edge.object_id == object_id
        ), None)
        if delegation is None:
            return ([], [])
        deed = evidence if isinstance(evidence, Deed) else self._derived_deed(evidence)
        if deed is None:
            return ([], [])
        performed = self._performed_edge(deed)
        if performed is None:
            return ([], [])
        return ([claim_actor, deed_actor, deed.node_id], [delegation.edge_id, performed.edge_id])

    def _derived_deed(self, observation: Observation) -> Optional[Deed]:
        edge = next((
            e for e in self.edges.values()
            if e.edge_kind == "derived-from" and e.source_id == observation.node_id
            and e.target_id in self.deeds
        ), None)
        return self.deeds.get(edge.target_id) if edge else None

    def _valid_semantic_edge(self, claim: Claim, edge: Edge):
        evidence = self._node(edge.source_id)
        if not isinstance(evidence, (Deed, Observation)) or self._is_superseded(edge.source_id):
            return None
        allowed = _RESOLVER_PREDICATES.get(edge.resolver_id, frozenset())
        if claim.predicate not in allowed or edge.resolver_version != RESOLVER_VERSION:
            return None
        claim_target_edges = self.target_edges(claim.node_id)
        evidence_target_edges = self.target_edges(edge.source_id)
        common = {
            c.target_id for c in claim_target_edges
        } & {e.target_id for e in evidence_target_edges}
        if not common or edge.object_id not in common:
            return None
        if isinstance(evidence, Deed) and evidence.source_event_id == claim.source_event_id:
            return None
        derived_nodes: list[str] = []
        derived_edges: list[str] = []
        if isinstance(evidence, Observation) and evidence.source == "tool-result":
            derived = next((
                e for e in self.edges.values()
                if e.edge_kind == "derived-from" and e.source_id == evidence.node_id
                and e.target_id in self.deeds
            ), None)
            if derived is None:
                return None
            deed = self.deeds[derived.target_id]
            if deed.source_event_id == claim.source_event_id:
                return None
            derived_nodes.append(deed.node_id)
            derived_edges.append(derived.edge_id)

        delegation_nodes: list[str] = []
        delegation_edges: list[str] = []
        if getattr(evidence, "actor_id", "") != claim.actor_id:
            delegation_nodes, delegation_edges = self._delegation_path(
                claim, evidence, edge.object_id,
            )
            if not delegation_edges:
                return None

        claim_target = next(e for e in claim_target_edges if e.target_id == edge.object_id)
        evidence_target = next(e for e in evidence_target_edges if e.target_id == edge.object_id)
        path_nodes = [claim.node_id, edge.object_id, evidence.node_id]
        path_nodes.extend(derived_nodes)
        path_nodes.extend(delegation_nodes)
        path_edges = [claim_target.edge_id, evidence_target.edge_id, edge.edge_id]
        path_edges.extend(derived_edges)
        path_edges.extend(delegation_edges)
        return (
            tuple(dict.fromkeys(path_nodes)),
            tuple(dict.fromkeys(path_edges)),
            evidence,
        )

    def adjudicate(self, claim_id: str) -> Adjudication:
        claim = self.claims.get(claim_id)
        if claim is None:
            return Adjudication(claim_id=claim_id, verdict=Verdict.NOT_EVALUABLE)
        candidates = []
        for edge in self.semantic_edges(claim_id):
            valid = self._valid_semantic_edge(claim, edge)
            if valid is not None:
                nodes, edges, evidence = valid
                candidates.append((edge, nodes, edges, evidence))
        if not candidates:
            return Adjudication(
                claim_id=claim_id,
                verdict=Verdict.NOT_EVALUABLE,
                reason="no valid predicate-and-target support path",
                path_node_ids=(claim.node_id,),
            )
        candidates.sort(key=lambda item: _event_order(
            getattr(item[3], "source_event_id", None)
        ))
        latest_order = _event_order(getattr(candidates[-1][3], "source_event_id", None))
        latest = [item for item in candidates
                  if _event_order(getattr(item[3], "source_event_id", None)) == latest_order]
        chosen = next((item for item in latest if item[0].edge_kind == "contradicts"), latest[-1])
        edge, nodes, edges, evidence = chosen
        verdict = Verdict.CONTRADICTED if edge.edge_kind == "contradicts" else Verdict.CERTIFIED
        return Adjudication(
            claim_id=claim_id,
            verdict=verdict,
            evidence_id=evidence.node_id,
            resolver_id=edge.resolver_id,
            resolver_version=edge.resolver_version,
            reason=edge.reason,
            path_node_ids=nodes,
            path_edge_ids=edges,
        )


def node_to_row(node) -> dict:
    data = asdict(node)
    kind = {
        Claim: "claim",
        Deed: "deed",
        Observation: "observation",
        ObjectNode: "object",
    }.get(type(node))
    if kind is None:
        raise TypeError(f"unsupported claim-graph node: {type(node).__name__}")
    data.update({"kind": kind, "graph_schema_version": GRAPH_SCHEMA_VERSION})
    return data


def edge_to_row(edge: Edge) -> dict:
    data = asdict(edge)
    data.update({"kind": "edge", "graph_schema_version": GRAPH_SCHEMA_VERSION})
    return data


def row_to_graph_value(row: Mapping):
    if row.get("graph_schema_version") != GRAPH_SCHEMA_VERSION:
        return None
    kind = row.get("kind")
    allowed = {
        "claim": Claim,
        "deed": Deed,
        "observation": Observation,
        "object": ObjectNode,
        "edge": Edge,
    }
    cls = allowed.get(kind)
    if cls is None:
        return None
    fields = cls.__dataclass_fields__
    values = {key: row.get(key) for key in fields}
    if cls is Deed:
        values["actions"] = tuple(values.get("actions") or ())
    try:
        return cls(**values)
    except (TypeError, ValueError):
        return None


def add_claim_bundle(graph: ClaimGraph, claim: Claim, target: ObjectNode) -> None:
    graph.add_object(target)
    graph.add_claim(claim)
    graph.add_edge(Edge.make(
        session_id=claim.session_id,
        edge_kind="asserts",
        source_id=f"event:{claim.session_id}:{claim.source_event_id}",
        target_id=claim.node_id,
        resolver_id="host-stop",
        resolver_version=RESOLVER_VERSION,
        reason="host-captured Stop event contains this exact claim span",
        source_event_id=claim.source_event_id,
    ))
    graph.add_edge(Edge.make(
        session_id=claim.session_id,
        edge_kind="targets",
        source_id=claim.node_id,
        target_id=target.node_id,
        resolver_id="claim-parser",
        resolver_version=RESOLVER_VERSION,
        reason=f"claim parser normalized {target.object_type} target",
        object_id=target.node_id,
        source_event_id=claim.source_event_id,
    ))


def add_deed_bundle(graph: ClaimGraph, deed: Deed, targets: Sequence[ObjectNode]) -> None:
    graph.add_deed(deed)
    actor = graph.add_object(ObjectNode.make(
        deed.session_id, "actor", deed.actor_id, deed.actor_id,
    ))
    graph.add_edge(Edge.make(
        session_id=deed.session_id,
        edge_kind="performed",
        source_id=actor.node_id,
        target_id=deed.node_id,
        resolver_id="host-posttool",
        resolver_version=RESOLVER_VERSION,
        reason="actor performed this settled PostToolUse deed",
        source_event_id=deed.source_event_id,
    ))
    for target in targets:
        graph.add_object(target)
        graph.add_edge(Edge.make(
            session_id=deed.session_id,
            edge_kind="targets",
            source_id=deed.node_id,
            target_id=target.node_id,
            resolver_id="deed-normalizer",
            resolver_version=RESOLVER_VERSION,
            reason=f"settled deed names exact {target.object_type} target",
            object_id=target.node_id,
            source_event_id=deed.source_event_id,
        ))


def add_observation_bundle(graph: ClaimGraph, observation: Observation, target: ObjectNode,
                           *, deed: Optional[Deed] = None) -> None:
    graph.add_object(target)
    prior = [
        obs for obs in graph.observations.values()
        if obs.predicate == observation.predicate and obs.target_id == observation.target_id
        and _event_order(obs.source_event_id) < _event_order(observation.source_event_id)
    ]
    graph.add_observation(observation)
    graph.add_edge(Edge.make(
        session_id=observation.session_id,
        edge_kind="targets",
        source_id=observation.node_id,
        target_id=target.node_id,
        resolver_id=observation.resolver_id,
        resolver_version=observation.resolver_version,
        reason=f"observation concerns exact {target.object_type} target",
        object_id=target.node_id,
        source_event_id=observation.source_event_id,
    ))
    if deed is not None:
        graph.add_edge(Edge.make(
            session_id=observation.session_id,
            edge_kind="derived-from",
            source_id=observation.node_id,
            target_id=deed.node_id,
            resolver_id=observation.resolver_id,
            resolver_version=observation.resolver_version,
            reason="observation derived from this settled deed result",
            object_id=target.node_id,
            source_event_id=observation.source_event_id,
        ))
    if prior:
        latest = max(prior, key=lambda obs: _event_order(obs.source_event_id))
        graph.add_edge(Edge.make(
            session_id=observation.session_id,
            edge_kind="supersedes",
            source_id=observation.node_id,
            target_id=latest.node_id,
            resolver_id=observation.resolver_id,
            resolver_version=observation.resolver_version,
            reason="newer evidence supersedes older evidence only for the same predicate and target",
            object_id=target.node_id,
            source_event_id=observation.source_event_id,
        ))


_ACTION_RX = re.compile(
    r"\bI\s+(?P<verb>ran|executed|installed|fetched|cloned|pulled|pushed|deployed|launched)\s+"
    r"(?P<obj>`[^`]+`|\S+)", re.IGNORECASE,
)
_ACTION_NEG_RX = re.compile(r"\b(?:not|never|without)\b|n't", re.IGNORECASE)
_ACTION_FUTURE_RX = re.compile(
    r"\b(?:will|going to|plan to|about to|let me)\b|i'?ll", re.IGNORECASE,
)
_PRIOR_TURN_RX = re.compile(
    r"\b(?:earlier|previously|already|before|last\s+turn|previous\s+turn|prior\s+turn|"
    r"this\s+session|in\s+the\s+last\s+turn|in\s+the\s+previous\s+turn|a\s+moment\s+ago)\b",
    re.IGNORECASE,
)
_TEST_NAME_RX = re.compile(r"\btest_[A-Za-z0-9_]+")
_PASS_PRED_RX = re.compile(r"\b(?:pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b", re.IGNORECASE)
_MERGE_PR_RX = re.compile(
    r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s+)?"
    r"(?:PR|pull\s+request)?\s*#?(?P<number>\d+)\b", re.IGNORECASE,
)
_OWNER_REPO_RX = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
_BRANCH_RX = re.compile(
    r"\bpushed\b(?:(?![.!?\n]).){0,80}?\b(?:to|branch)\s+[`'\"]?"
    r"(?:origin/)?([A-Za-z0-9][A-Za-z0-9._/-]*)", re.IGNORECASE,
)
_URL_RX = re.compile(r"https?://[^\s`'\"),;]+", re.IGNORECASE)
_PORT_RX = re.compile(r"\bport\s*[:#]?\s*(\d{2,5})\b|(?<!\w):(\d{2,5})\b", re.IGNORECASE)
_REC_TEST_RX = re.compile(
    r"(?:^|\n)(?P<lead>FAILED|ERROR|PASSED)\s+\S*?::(?P<name1>test_[A-Za-z0-9_]+)"
    r"|::(?P<name2>test_[A-Za-z0-9_]+)\b[^\n]*?\b(?P<trail>FAILED|ERROR|PASSED)\b",
    re.MULTILINE,
)


def _distinctive_action_object(raw: str) -> bool:
    if raw.startswith("`"):
        return True
    value = raw.strip("`'\".,;:)(")
    return bool(
        "/" in value or value.endswith(".py") or value.startswith("http")
        or re.search(r"\.\w{2,5}$", value)
    )


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(mark, 0, start) for mark in (". ", "! ", "? ", "\n")) + 1
    stops = [idx for idx in (
        text.find(". ", end), text.find("! ", end), text.find("? ", end), text.find("\n", end),
    ) if idx >= 0]
    right = min(stops) + 1 if stops else len(text)
    return (left, right)


def _unknown_target(session_id: str, predicate: str, span_text: str) -> ObjectNode:
    return ObjectNode.make(
        session_id, "unknown", f"{predicate}:{sha256_text(span_text)}", span_text,
    )


def canonical_path(value: str, cwd: Optional[str]) -> str:
    value = normalize_path(value)
    if not value:
        return ""
    if cwd and not os.path.isabs(value):
        return normalize_path(os.path.realpath(os.path.join(cwd, value)))
    return normalize_path(os.path.realpath(value)) if os.path.isabs(value) else value


def _canonical_argv(argv: Sequence[str]) -> str:
    effective = _effective_argv(argv)
    normalized = []
    for index, token in enumerate(effective):
        token = token[2:] if token.startswith("./") else token
        if index == 0:
            token = token.replace("\\", "/")
        normalized.append(token)
    return canonical_json(normalized)


def canonical_command(value: str) -> str:
    segments = _shell_segments(value or "")
    if not segments:
        try:
            return _canonical_argv(shlex.split(value or ""))
        except ValueError:
            return canonical_json([])
    return canonical_json([json.loads(_canonical_argv(argv)) for argv, _operator in segments])


def _command_objects(session_id: str, command: str) -> list[ObjectNode]:
    out: dict[str, ObjectNode] = {}
    segments = _shell_segments(command)
    if segments:
        out_obj = ObjectNode.make(session_id, "command", canonical_command(command), command)
        out[out_obj.node_id] = out_obj
    for argv, _operator in segments:
        effective = _effective_argv(argv)
        if not effective:
            continue
        executable = effective[0].replace("\\", "/")
        executable = executable[2:] if executable.startswith("./") else executable
        obj = ObjectNode.make(session_id, "executable", executable, executable)
        out[obj.node_id] = obj
        program = executable.rsplit("/", 1)[-1]
        if program in {"bash", "sh", "zsh", "python", "python3"}:
            for arg in effective[1:]:
                cleaned = arg[2:] if arg.startswith("./") else arg
                if "/" in cleaned or cleaned.endswith((".sh", ".py")):
                    script_obj = ObjectNode.make(session_id, "executable", cleaned, cleaned)
                    out[script_obj.node_id] = script_obj
                    break
        for token in effective[1:]:
            cleaned = token.strip("`'\".,;:)(")
            if re.fullmatch(r"(?:release|version|v)[-_]?[A-Za-z0-9][A-Za-z0-9._-]*", cleaned,
                            re.IGNORECASE):
                release = ObjectNode.make(session_id, "release", cleaned.lower(), cleaned)
                out[release.node_id] = release
    return list(out.values())


def _endpoint_objects(session_id: str, text: str) -> list[ObjectNode]:
    out: dict[str, ObjectNode] = {}
    for match in _URL_RX.finditer(text or ""):
        url = match.group(0).rstrip("/.")
        obj = ObjectNode.make(session_id, "endpoint", url.lower(), url)
        out[obj.node_id] = obj
        port_match = re.search(r":(\d{2,5})(?:/|$)", url)
        if port_match:
            port = port_match.group(1)
            port_obj = ObjectNode.make(session_id, "endpoint-port", port, f"port {port}")
            out[port_obj.node_id] = port_obj
    for match in _PORT_RX.finditer(text or ""):
        port = match.group(1) or match.group(2)
        obj = ObjectNode.make(session_id, "endpoint-port", port, f"port {port}")
        out[obj.node_id] = obj
    return list(out.values())


def repository_identity(cwd: Optional[str], *, run=subprocess.run) -> str:
    if not cwd:
        return ""
    try:
        root = run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3.0,
        )
        remote = run(
            ["git", "-C", str(cwd), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=3.0,
        )
    except Exception:
        return ""
    if root.returncode != 0 or not root.stdout.strip():
        return ""
    root_value = os.path.realpath(root.stdout.strip())
    remote_value = remote.stdout.strip() if remote.returncode == 0 else ""
    return canonical_json({"root": root_value, "remote": remote_value})


def _repo_ref_object(session_id: str, cwd: Optional[str], branch: str,
                     *, run=subprocess.run) -> ObjectNode:
    identity = repository_identity(cwd, run=run)
    value = canonical_json({
        "repository": identity,
        "remote": "origin",
        "ref": f"refs/heads/{branch}",
    })
    return ObjectNode.make(session_id, "repository-ref", value, f"origin/{branch}")


def _make_claim(graph: ClaimGraph, *, source_event_id, actor_id: str, full_text: str,
                start: int, end: int, predicate: str, target: ObjectNode,
                tense: str = "past") -> Claim:
    claim = Claim.make(
        session_id=graph.session_id,
        source_event_id=source_event_id,
        actor_id=actor_id,
        full_text=full_text,
        span_start=start,
        span_end=end,
        predicate=predicate,
        target=target,
        tense=tense,
    )
    add_claim_bundle(graph, claim, target)
    return claim


def extract_claims(graph: ClaimGraph, text: str, *, source_event_id, actor_id: str,
                   cwd: Optional[str] = None, run=subprocess.run) -> list[Claim]:
    """Extract typed claims with exact spans from one host-captured Stop message."""
    if not text:
        return []
    created: list[Claim] = []
    spans = _code_spans(text)

    for match in _ACTION_RX.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        pre = text[max(0, match.start() - 24):match.start()]
        if _ACTION_NEG_RX.search(pre) or _ACTION_FUTURE_RX.search(pre):
            continue
        sent_start, sent_end = _sentence_bounds(text, match.start(), match.end())
        if _PRIOR_TURN_RX.search(text[sent_start:sent_end]):
            continue
        raw = match.group("obj")
        if not _distinctive_action_object(raw):
            continue
        value = raw.strip("`'\".,;:)(")
        if any(char.isspace() for char in value):
            target = ObjectNode.make(graph.session_id, "command", canonical_command(value), value)
        elif value.startswith("http"):
            target = ObjectNode.make(graph.session_id, "url", value.lower(), value)
        else:
            normalized = value[2:] if value.startswith("./") else value
            target = ObjectNode.make(graph.session_id, "executable", normalized, value)
        verb = match.group("verb").lower()
        predicate = {
            "ran": "action.run", "executed": "action.execute", "installed": "action.install",
            "fetched": "action.fetch", "cloned": "action.clone", "pulled": "action.pull",
            "launched": "action.launch", "deployed": "action.deploy", "pushed": "action.run",
        }[verb]
        created.append(_make_claim(
            graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
            start=match.start(), end=match.end(), predicate=predicate, target=target,
        ))

    if _PROCESS_START_VERB_RX.search(text):
        for match in _RUNNING_CLAIM_RX.finditer(text):
            if any(start <= match.start() < end for start, end in spans):
                continue
            clause = _SENTENCE_SPLIT_RX.split(text[max(0, match.start() - 70):match.start()])[-1]
            if _NEGATION_RX.search(clause) or _ADV_FORWARD_RX.search(clause):
                continue
            sent_start, sent_end = _sentence_bounds(text, match.start(), match.end())
            endpoint_targets = _endpoint_objects(graph.session_id, text[sent_start:sent_end])
            target = endpoint_targets[-1] if endpoint_targets else _unknown_target(
                graph.session_id, "service.running", text[sent_start:sent_end],
            )
            created.append(_make_claim(
                graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
                start=match.start(), end=match.end(), predicate="service.running", target=target,
                tense="present",
            ))
            break

    for match in _RUN_INTENT_CLAIM_RX.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        if _NEGATION_RX.search(match.group(0)):
            continue
        if _RUN_INTENT_IDIOM_VETO_RX.search(text[match.end():match.end() + 40]):
            continue
        sent_start, sent_end = _sentence_bounds(text, match.start(), match.end())
        if text[sent_end - 1:sent_end] == "?":
            continue
        sentence = text[sent_start:sent_end]
        tail = text[match.end():sent_end].strip(" \t`'\".,;:()")
        verb_text = match.group(0).lower()
        target: ObjectNode
        predicate = "promise.run"
        if "deploy" in verb_text:
            predicate = "promise.deploy"
            code = re.search(r"`([^`]+)`", text[match.end():sent_end])
            candidate = code.group(1) if code else ""
            if not candidate:
                token = re.search(r"\b(?:release|version|v)[-_]?[A-Za-z0-9][A-Za-z0-9._-]*\b",
                                  text[match.end():sent_end], re.IGNORECASE)
                candidate = token.group(0) if token else ""
            target = (ObjectNode.make(graph.session_id, "release", candidate.lower(), candidate)
                      if candidate else _unknown_target(graph.session_id, predicate, sentence))
        elif re.search(r"\btests?|pytest|npm\s+test|test\s+suite\b", tail, re.IGNORECASE):
            predicate = "promise.test"
            target = ObjectNode.make(graph.session_id, "test-suite", canonical_path(".", cwd), "test suite")
        elif any(word in verb_text for word in ("launch", "spin up", "bring up", "boot", "kick off",
                                                "fire up", "stand up")):
            predicate = "promise.launch"
            endpoints = _endpoint_objects(graph.session_id, sentence)
            target = endpoints[-1] if endpoints else _unknown_target(graph.session_id, predicate, sentence)
        elif "restart" in verb_text:
            predicate = "promise.restart"
            endpoints = _endpoint_objects(graph.session_id, sentence)
            target = endpoints[-1] if endpoints else _unknown_target(graph.session_id, predicate, sentence)
        elif tail:
            code = re.search(r"`([^`]+)`", text[match.end():sent_end])
            command = code.group(1) if code else tail
            target = ObjectNode.make(graph.session_id, "command", canonical_command(command), command)
        else:
            target = _unknown_target(graph.session_id, predicate, sentence)
        created.append(_make_claim(
            graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
            start=match.start(), end=sent_end, predicate=predicate, target=target, tense="future",
        ))

    shipping_matches = sorted(
        list(_SHIPPED_ACTION_CLAIM_RX.finditer(text)) + list(_SHIPPED_STATE_CLAIM_RX.finditer(text)),
        key=lambda item: item.start(),
    )
    for match in shipping_matches:
        if any(start <= match.start() < end for start, end in spans):
            continue
        clause = _SENTENCE_SPLIT_RX.split(text[max(0, match.start() - 90):match.start()])[-1] + match.group(0)
        if _NEGATION_RX.search(clause) or _ADV_FORWARD_RX.search(clause):
            continue
        sent_start, sent_end = _sentence_bounds(text, match.start(), match.end())
        sentence = text[sent_start:sent_end]
        lower = match.group(0).lower()
        if "merge" in lower:
            predicate = "remote.merge"
            pr = _MERGE_PR_RX.search(sentence)
            repo = _OWNER_REPO_RX.search(sentence)
            number = pr.group("number") if pr else ""
            repo_value = repo.group(1).lower() if repo else ""
            if repo_value and number:
                target = ObjectNode.make(
                    graph.session_id, "repository-pr", f"{repo_value}#{int(number)}",
                    f"{repo.group(1)} PR #{int(number)}",
                )
            elif number:
                target = ObjectNode.make(graph.session_id, "pr-number", str(int(number)), f"PR #{int(number)}")
            else:
                target = _unknown_target(graph.session_id, predicate, sentence)
        elif "push" in lower:
            predicate = "remote.push"
            branch_match = _BRANCH_RX.search(sentence)
            target = (_repo_ref_object(graph.session_id, cwd, branch_match.group(1), run=run)
                      if branch_match else _unknown_target(graph.session_id, predicate, sentence))
        else:
            action = next((word for word in ("published", "deployed", "shipped", "released")
                           if word in lower), "shipped")
            predicate = f"remote.{action.rstrip('d').rstrip('e')}"
            code = re.search(r"`([^`]+)`", sentence)
            target = (ObjectNode.make(graph.session_id, "release", code.group(1).lower(), code.group(1))
                      if code else _unknown_target(graph.session_id, predicate, sentence))
        created.append(_make_claim(
            graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
            start=match.start(), end=sent_end, predicate=predicate, target=target,
            tense="present" if re.search(r"\b(?:is|are|['’]s|['’]re)\b", lower) else "past",
        ))
        break

    for sent in _SENTENCE_SPLIT_RX.split(text):
        if not _PASS_PRED_RX.search(sent):
            continue
        sent_offset = text.find(sent)
        for name_match in _TEST_NAME_RX.finditer(sent):
            name = name_match.group(0)
            window = sent[max(0, name_match.start() - 80):name_match.end() + 60]
            if not _PASS_PRED_RX.search(window) or re.search(
                r"\b(?:not|never|fail(?:s|ed|ing)?|will|expect(?:s|ed|ing)?)\b", window,
                re.IGNORECASE,
            ):
                continue
            target = ObjectNode.make(graph.session_id, "named-test", name, name)
            created.append(_make_claim(
                graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
                start=sent_offset + name_match.start(), end=sent_offset + name_match.end(),
                predicate="test.pass.named", target=target, tense="present",
            ))

    for match in _GREEN_CLAIM_RX.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        pre = text[max(0, match.start() - 60):match.start()]
        clause = _SENTENCE_SPLIT_RX.split(pre)[-1].rsplit(",", 1)[-1]
        if _NEGATION_RX.search(clause) or _ADV_FORWARD_RX.search(clause):
            continue
        tokens = re.findall(r"\w+", text[max(0, match.start() - 40):match.start()])
        if tokens and (tokens[-1].isdigit() or tokens[-1].lower() not in _GREEN_UNIVERSAL_PREMOD):
            continue
        target = ObjectNode.make(graph.session_id, "test-suite", canonical_path(".", cwd), "test suite")
        created.append(_make_claim(
            graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
            start=match.start(), end=match.end(), predicate="test.pass.suite", target=target,
            tense="present",
        ))
        break

    for location, start, _end in detect_locations(text):
        before = text[max(0, start - 70):start]
        accepted = None
        for verb_match in _PRODUCE_VERB_RX.finditer(before):
            prefix = before[:verb_match.start()]
            between = before[verb_match.end():]
            if _BE_AUX_RX.search(prefix) or _CLAUSE_BREAK_RX.search(between):
                continue
            if _FORWARD_FRAME_RX.search(prefix[-40:]) or _NEG_FRAME_RX.search(prefix[-40:]):
                continue
            accepted = verb_match
        if accepted is None:
            continue
        target_value = canonical_path(location, cwd)
        target = ObjectNode.make(graph.session_id, "path", target_value, location)
        created.append(_make_claim(
            graph, source_event_id=source_event_id, actor_id=actor_id, full_text=text,
            start=start, end=start + len(location), predicate="file.produced", target=target,
        ))
        break

    unique: dict[str, Claim] = {}
    for claim in created:
        unique.setdefault(claim.node_id, claim)
    return list(unique.values())


def _response_status(response) -> str:
    if not isinstance(response, Mapping):
        return "unknown"
    if response.get("interrupted") is True:
        return "failed"
    exit_code = response.get("exitCode", response.get("exit"))
    if exit_code is not None and exit_code != 0:
        return "failed"
    if any(response.get(key) not in (None, "", False) for key in
           ("error", "error_code", "is_error")):
        return "failed"
    return "success" if response else "unknown"


def _deed_actions(tool: str, tool_input: Mapping) -> set[str]:
    actions: set[str] = set()
    command = str(tool_input.get("command", "") or "") if isinstance(tool_input, Mapping) else ""
    if tool == "Bash":
        actions.add("action.run")
        lower = command.lower()
        if _command_runs_tests(command):
            actions.add("test.run")
        if _command_pushes_git(command):
            actions.add("remote.push")
        if re.search(r"(?:^|[/_.-])deploy(?:\.sh|\b)|\b(?:kubectl\s+apply|helm\s+(?:install|upgrade))\b", lower):
            actions.add("remote.deploy")
        if re.search(r"(?:^|[/_.-])publish(?:\.sh|\b)|\b(?:npm|cargo|twine)\s+publish\b", lower):
            actions.add("remote.publish")
        if _PROCESS_LIFECYCLE_CMD_RX.search(command):
            actions.add("service.lifecycle")
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        actions.add("file.write")
    elif tool.endswith("merge_pull_request"):
        actions.add("remote.merge")
    elif tool.endswith("push_files"):
        actions.add("remote.push")
    else:
        actions.add(f"tool.{tool.lower()}")
    return actions


def _merge_target(session_id: str, tool_input: Mapping) -> Optional[ObjectNode]:
    owner = str(tool_input.get("owner", "") or "").strip()
    repo = str(tool_input.get("repo", tool_input.get("repository", "")) or "").strip()
    number = tool_input.get("pullNumber", tool_input.get("pull_number",
              tool_input.get("pr_number", tool_input.get("number"))))
    if isinstance(repo, str) and "/" in repo and not owner:
        owner, repo = repo.split("/", 1)
    try:
        number_value = str(int(number))
    except (TypeError, ValueError):
        number_value = ""
    if owner and repo and number_value:
        value = f"{owner.lower()}/{repo.lower()}#{number_value}"
        return ObjectNode.make(session_id, "repository-pr", value, f"{owner}/{repo} PR #{number_value}")
    if number_value:
        return ObjectNode.make(session_id, "pr-number", number_value, f"PR #{number_value}")
    return None


def ingest_deed_event(graph: ClaimGraph, payload: Mapping, *, source_event_id,
                      cwd: Optional[str] = None) -> Optional[Deed]:
    if not isinstance(payload, Mapping) or payload.get("hook_event_name") != "PostToolUse":
        return None
    tool = str(payload.get("tool_name", "") or "")
    if not tool:
        return None
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}
    response = payload.get("tool_response")
    actor_id = canonical_actor_id(payload.get("agent_id"))
    actions = _deed_actions(tool, tool_input)
    deed = Deed.make(
        session_id=graph.session_id,
        source_event_id=source_event_id,
        actor_id=actor_id,
        tool=tool,
        tool_input=tool_input,
        tool_response=response,
        status=_response_status(response),
        actions=actions,
    )
    targets: list[ObjectNode] = []
    command = str(tool_input.get("command", "") or "")
    if tool == "Bash":
        targets.extend(_command_objects(graph.session_id, command))
        targets.extend(_endpoint_objects(graph.session_id, command))
        if _command_runs_tests(command):
            targets.append(ObjectNode.make(
                graph.session_id, "test-suite", canonical_path(".", cwd), "test suite",
            ))
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        path = tool_input.get("file_path", tool_input.get("notebook_path", ""))
        if path:
            targets.append(ObjectNode.make(
                graph.session_id, "path", canonical_path(str(path), cwd), str(path),
            ))
    elif tool.endswith("merge_pull_request"):
        target = _merge_target(graph.session_id, tool_input)
        if target:
            targets.append(target)
    elif tool.endswith("push_files"):
        branch = str(tool_input.get("branch", "") or "")
        if branch:
            targets.append(_repo_ref_object(graph.session_id, cwd, branch))
    add_deed_bundle(graph, deed, list({target.node_id: target for target in targets}.values()))

    if tool == "Bash":
        output = bash_output_text(response)
        if _command_runs_tests(command):
            suite_target = ObjectNode.make(
                graph.session_id, "test-suite", canonical_path(".", cwd), "test suite",
            )
            suite_status = "FAIL" if is_failing_testrun(output) else (
                "PASS" if deed.status == "success" else "UNKNOWN"
            )
            if suite_status != "UNKNOWN":
                suite_obs = Observation.make(
                    session_id=graph.session_id,
                    source_event_id=source_event_id,
                    actor_id=actor_id,
                    predicate="test.pass.suite",
                    target=suite_target,
                    status=suite_status,
                    resolver_id="suite-test",
                    source="tool-result",
                    value=output[-500:],
                )
                add_observation_bundle(graph, suite_obs, suite_target, deed=deed)
            if not _TEETH_FRAME_RX.search(output):
                for match in _REC_TEST_RX.finditer(output or ""):
                    name = match.group("name1") or match.group("name2")
                    marker = match.group("lead") or match.group("trail")
                    status = "PASS" if marker == "PASSED" else "FAIL"
                    target = ObjectNode.make(graph.session_id, "named-test", name, name)
                    observation = Observation.make(
                        session_id=graph.session_id,
                        source_event_id=source_event_id,
                        actor_id=actor_id,
                        predicate="test.pass.named",
                        target=target,
                        status=status,
                        resolver_id="named-test",
                        source="tool-result",
                        value=marker,
                    )
                    add_observation_bundle(graph, observation, target, deed=deed)

        endpoints = _endpoint_objects(graph.session_id, command)
        lower = command.lower()
        is_healthcheck = bool(re.search(
            r"\b(?:curl|wget|nc\s+-z|lsof\s+-i|netstat|ss\s+-|pgrep|docker\s+ps|"
            r"systemctl\s+status|pm2\s+(?:status|list))\b", lower,
        ))
        for target in endpoints:
            if is_healthcheck or (deed.status == "failed" and _PROCESS_LIFECYCLE_CMD_RX.search(command)):
                observation = Observation.make(
                    session_id=graph.session_id,
                    source_event_id=source_event_id,
                    actor_id=actor_id,
                    predicate="service.running",
                    target=target,
                    status="PASS" if is_healthcheck and deed.status == "success" else "FAIL",
                    resolver_id="service-endpoint",
                    source="tool-result",
                    value=deed.status,
                )
                add_observation_bundle(graph, observation, target, deed=deed)
    return deed


def history_event_id(row, index: int):
    if isinstance(row, (tuple, list)) and row:
        return row[0]
    if isinstance(row, Mapping):
        return row.get("id", row.get("source_event_id", f"history-{index}"))
    return f"history-{index}"


def ingest_history(graph: ClaimGraph, history: Sequence, *, cwd: Optional[str] = None,
                   include_stop_claims: bool = True) -> None:
    for index, row in enumerate(history or ()):
        payload = decode_history_row(row)
        if not isinstance(payload, Mapping):
            continue
        source_event_id = history_event_id(row, index)
        event = payload.get("hook_event_name")
        if event == "PostToolUse":
            ingest_deed_event(graph, payload, source_event_id=source_event_id,
                              cwd=(row[3] if isinstance(row, (tuple, list)) and len(row) > 3 else cwd))
        elif include_stop_claims and event in {"Stop", "SubagentStop"}:
            extract_claims(
                graph,
                str(payload.get("last_assistant_message", "") or ""),
                source_event_id=source_event_id,
                actor_id=canonical_actor_id(payload.get("agent_id")),
                cwd=(row[3] if isinstance(row, (tuple, list)) and len(row) > 3 else cwd),
            )


def observe_filesystem_claims(graph: ClaimGraph, claim_ids: Sequence[str], *, source_event_id,
                              fs_exists=None, fs_size=None) -> None:
    for claim_id in claim_ids:
        claim = graph.claims.get(claim_id)
        if claim is None or claim.predicate != "file.produced" or fs_exists is None:
            continue
        try:
            exists = bool(fs_exists(claim.target_value))
            size = fs_size(claim.target_value) if exists and fs_size is not None else None
        except Exception:
            continue
        status = "PRESENT" if exists and size != 0 else "ABSENT"
        target = graph.objects.get(claim.target_id)
        if target is None:
            continue
        observation = Observation.make(
            session_id=graph.session_id,
            source_event_id=source_event_id,
            actor_id="resolver:filesystem",
            predicate="file.produced",
            target=target,
            status=status,
            resolver_id="filesystem-path",
            source="filesystem",
            value=str(size if size is not None else ""),
        )
        add_observation_bundle(graph, observation, target)


def observe_push_claims(graph: ClaimGraph, claim_ids: Sequence[str], *, source_event_id,
                        cwd: Optional[str], run=subprocess.run) -> None:
    for claim_id in claim_ids:
        claim = graph.claims.get(claim_id)
        if claim is None or claim.predicate != "remote.push" or claim.target_type != "repository-ref":
            continue
        try:
            target_data = json.loads(claim.target_value)
            ref = target_data["ref"]
            local = run(
                ["git", "-C", str(cwd), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=3.0,
            )
            remote = run(
                ["git", "-C", str(cwd), "ls-remote", "--refs", "origin", ref],
                capture_output=True, text=True, timeout=3.0,
            )
        except Exception:
            continue
        local_sha = local.stdout.strip()
        fields = remote.stdout.strip().split()
        remote_sha = fields[0] if fields else ""
        if local.returncode != 0 or remote.returncode != 0 or not local_sha or not remote_sha:
            continue
        target = graph.objects.get(claim.target_id)
        if target is None:
            continue
        status = "MATCH" if local_sha == remote_sha else "MISMATCH"
        observation = Observation.make(
            session_id=graph.session_id,
            source_event_id=source_event_id,
            actor_id="resolver:git-remote",
            predicate="remote.push",
            target=target,
            status=status,
            resolver_id="git-remote-tip",
            source="git-ls-remote",
            value=canonical_json({"local_tip": local_sha, "remote_tip": remote_sha, "ref": ref}),
        )
        add_observation_bundle(graph, observation, target)


def _deed_matches_command_claim(deed: Deed, claim: Claim, graph: ClaimGraph) -> bool:
    if not any(action in deed.actions for action in {
        "action.run", "remote.deploy", "service.lifecycle", "test.run", "remote.push",
    }):
        return False
    return any(edge.target_id == claim.target_id for edge in graph.target_edges(deed.node_id))


def _matching_deeds(graph: ClaimGraph, claim: Claim, *, after: bool) -> list[Deed]:
    out = []
    claim_order = _event_order(claim.source_event_id)
    for deed in graph.deeds.values():
        deed_order = _event_order(deed.source_event_id)
        if after and deed_order <= claim_order:
            continue
        if not after and deed_order >= claim_order:
            continue
        out.append(deed)
    return out


def _add_semantic_edge(graph: ClaimGraph, *, evidence_id: str, claim: Claim, kind: str,
                       resolver_id: str, reason: str, source_event_id=None) -> Edge:
    edge = Edge.make(
        session_id=graph.session_id,
        edge_kind=kind,
        source_id=evidence_id,
        target_id=claim.node_id,
        resolver_id=resolver_id,
        resolver_version=RESOLVER_VERSION,
        reason=reason,
        object_id=claim.target_id,
        source_event_id=source_event_id,
    )
    graph.add_edge(edge)
    return edge


def _delegation_payloads(history: Sequence) -> list[tuple[object, Mapping]]:
    out = []
    for index, row in enumerate(history or ()):
        payload = decode_history_row(row)
        if not isinstance(payload, Mapping) or payload.get("hook_event_name") != "PostToolUse":
            continue
        if payload.get("tool_name") not in {"Agent", "Task", "Workflow"}:
            continue
        out.append((history_event_id(row, index), payload))
    return out


def add_explicit_delegations(graph: ClaimGraph, claims: Iterable[Claim], history: Sequence) -> None:
    """Create target-bound actor delegation edges from explicit settled Agent/Task events."""
    for event_id, payload in _delegation_payloads(history):
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), Mapping) else {}
        response = payload.get("tool_response") if isinstance(payload.get("tool_response"), Mapping) else {}
        delegated_id = (
            response.get("agent_id") or response.get("agentId") or response.get("subagent_id")
            or tool_input.get("agent_id") or tool_input.get("agentId") or tool_input.get("target_agent_id")
        )
        if not isinstance(delegated_id, str) or not delegated_id.strip():
            continue
        prompt = " ".join(str(tool_input.get(key, "") or "") for key in
                          ("prompt", "description", "task"))
        parent_actor = canonical_actor_id(payload.get("agent_id"))
        child_actor = canonical_actor_id(delegated_id)
        parent_obj = graph.add_object(ObjectNode.make(graph.session_id, "actor", parent_actor, parent_actor))
        child_obj = graph.add_object(ObjectNode.make(graph.session_id, "actor", child_actor, child_actor))
        for claim in claims:
            target = graph.objects.get(claim.target_id)
            if target is None or target.object_type == "unknown":
                continue
            display = target.display_value.lower()
            canonical = target.canonical_value.lower()
            prompt_lower = prompt.lower()
            tokens = [token for token in re.split(r"[^a-z0-9_.#/-]+", display) if len(token) >= 2]
            if not ((canonical and canonical in prompt_lower) or (tokens and all(t in prompt_lower for t in tokens))):
                continue
            graph.add_edge(Edge.make(
                session_id=graph.session_id,
                edge_kind="delegated-to",
                source_id=parent_obj.node_id,
                target_id=child_obj.node_id,
                resolver_id="explicit-delegation",
                resolver_version=RESOLVER_VERSION,
                reason="settled Agent/Task event explicitly delegated this exact target",
                object_id=claim.target_id,
                source_event_id=event_id,
            ))


def link_claims(graph: ClaimGraph, *, history: Sequence = ()) -> None:
    """Run the closed resolver set and add only predicate-and-target semantic edges."""
    add_explicit_delegations(graph, graph.claims.values(), history)
    for claim in graph.claims.values():
        if claim.target_type == "unknown":
            continue
        if claim.predicate.startswith("action."):
            for deed in _matching_deeds(graph, claim, after=False):
                if _deed_matches_command_claim(deed, claim, graph):
                    _add_semantic_edge(
                        graph, evidence_id=deed.node_id, claim=claim, kind="supports",
                        resolver_id="exact-command",
                        reason="settled deed has the same canonical command/executable target",
                        source_event_id=deed.source_event_id,
                    )
        elif claim.predicate.startswith("promise."):
            for deed in _matching_deeds(graph, claim, after=True):
                matches = False
                if claim.predicate == "promise.test":
                    matches = "test.run" in deed.actions
                elif claim.predicate == "promise.deploy":
                    matches = "remote.deploy" in deed.actions and any(
                        edge.target_id == claim.target_id for edge in graph.target_edges(deed.node_id)
                    )
                elif claim.predicate in {"promise.launch", "promise.restart"}:
                    matches = "service.lifecycle" in deed.actions and any(
                        edge.target_id == claim.target_id for edge in graph.target_edges(deed.node_id)
                    )
                else:
                    matches = _deed_matches_command_claim(deed, claim, graph)
                if matches:
                    _add_semantic_edge(
                        graph, evidence_id=deed.node_id, claim=claim, kind="supports",
                        resolver_id="run-promise",
                        reason="later settled deed has the promised action and exact target identity",
                        source_event_id=deed.source_event_id,
                    )
        elif claim.predicate == "remote.merge":
            for deed in _matching_deeds(graph, claim, after=False):
                if "remote.merge" not in deed.actions or deed.status != "success":
                    continue
                if not any(edge.target_id == claim.target_id for edge in graph.target_edges(deed.node_id)):
                    continue
                _add_semantic_edge(
                    graph, evidence_id=deed.node_id, claim=claim, kind="supports",
                    resolver_id="github-merge",
                    reason="successful merge deed names the same owner/repository and PR number",
                    source_event_id=deed.source_event_id,
                )
        elif claim.predicate in {"service.running", "remote.push", "test.pass.named",
                                 "test.pass.suite", "file.produced"}:
            resolver = {
                "service.running": "service-endpoint",
                "remote.push": "git-remote-tip",
                "test.pass.named": "named-test",
                "test.pass.suite": "suite-test",
                "file.produced": "filesystem-path",
            }[claim.predicate]
            for observation in graph.observations.values():
                if observation.predicate != claim.predicate or observation.target_id != claim.target_id:
                    continue
                support_statuses = {"PASS", "MATCH", "PRESENT"}
                contradict_statuses = {"FAIL", "MISMATCH", "ABSENT"}
                if observation.status in support_statuses:
                    kind = "supports"
                elif observation.status in contradict_statuses:
                    kind = "contradicts"
                else:
                    continue
                _add_semantic_edge(
                    graph, evidence_id=observation.node_id, claim=claim, kind=kind,
                    resolver_id=resolver,
                    reason=(f"{observation.status.lower()} observation has the same predicate "
                            "and canonical target"),
                    source_event_id=observation.source_event_id,
                )


def build_ephemeral_graph(text: str, *, history: Sequence = (), session_id: str = "ephemeral",
                          source_event_id=None, actor_id: str = "agent:main",
                          cwd: Optional[str] = None, fs_exists=None, fs_size=None,
                          observe_push: bool = False, run=subprocess.run) -> tuple[ClaimGraph, list[str]]:
    graph = ClaimGraph(session_id=session_id)
    ingest_history(graph, history, cwd=cwd)
    if source_event_id is None:
        orders = [_event_order(history_event_id(row, idx))[0] for idx, row in enumerate(history or ())]
        source_event_id = (max(orders) + 1) if orders else 1
    claims = extract_claims(
        graph, text, source_event_id=source_event_id, actor_id=actor_id, cwd=cwd, run=run,
    )
    claim_ids = [claim.node_id for claim in claims]
    observe_filesystem_claims(
        graph, claim_ids, source_event_id=source_event_id, fs_exists=fs_exists, fs_size=fs_size,
    )
    if observe_push:
        observe_push_claims(
            graph, claim_ids, source_event_id=source_event_id, cwd=cwd, run=run,
        )
    link_claims(graph, history=history)
    return graph, claim_ids
