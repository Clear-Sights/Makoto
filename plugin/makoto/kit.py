"""makoto.kit — the shared check-building kit: L1 predicate factories and AST
primitives, tool/event I/O parsing, deterministic location/quantity/subject
primitives, transient-vs-deterministic failure classification, per-test verdict
delta, and shared gate helpers (the `GateContext` schema itself lives in
`context.py`).

Stdlib only; no HTTP, no LLM (Knight-Leveson hot-path invariant). Imports only L0
(`makoto.vocab`, `makoto.core._shell`); `compute_delta`'s reuse of namedTestTeeth's
parsers stays a call-time import so the kit never carries an import-time edge into
a named check module.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import textwrap
from typing import Callable, Optional

from makoto.core._shell import _command_runs_tests
from makoto.vocab import (
    _TEST_RUNNER_RX,  # pinned by tests/test_lexicons.py
    _FAILURE_SUMMARY_RX,
    _FAILURE_MARKER_RX,
    _ANSI_SGR_RX,
    _EMPTY_OK,
    _MAKOTO_ALLOW_RX,
    _MAKOTO_ALLOW_REASON_RX,
    _PATH_EXT,
    Finding,
    JWT_CALLEE_RX,
    # recorded per-test verdict parsers; compute_delta/current_named_verdicts read them.
    _TEETH_FRAME_RX,
    _TEETH_SCOPE_AFTER,
    _TEETH_SCOPE_BEFORE,
    _REC_FAIL_LEAD_RX,
    _REC_FAIL_TRAIL_RX,
    _REC_PASS_LEAD_RX,
    _REC_PASS_TRAIL_RX,
    recorded_failed_names,
    recorded_passed_names,
)

# `pattern: Check` below is a hint only, never a real import: this L1 module's layering
# firewall (tests/lib/test_factories.py) bars importing the registry (L2+) even for a type
# hint. `from __future__ import annotations` means the name is never evaluated at runtime.


# ---- deterministic check primitives ------------------------------------------------------------
# Location is normalized-path EQUALITY (not substring — the fakeexcuse firewall).
# Quantity is a number compare. Subject-binding gates retraction reasons.

def normalize_path(p: str) -> str:
    """Case-folded, normalized, trailing-separator-stripped path for equality.

    Separators are forced to forward-slash so a claim/commitment/touched identity is
    platform-stable: os.path.normpath emits '\\' on Windows, which would make the same
    logical path mismatch its POSIX-authored form (Windows-portability fix)."""
    if not p:
        return ""
    # `.lower()` does the case-folding the docstring promises: `os.path.normcase` is the
    # identity on POSIX, which silently made every equality/suffix gate built on this
    # case-sensitive on the platform the hook actually runs on.
    return os.path.normcase(os.path.normpath(p.strip())).lower().rstrip("/\\").replace("\\", "/")


# A location is a GENUINE FILE PATH: a known-extension filename, optionally with a
# directory prefix (relative, absolute, ~/, or ./), OR a well-known extensionless file.
# It is NOT a version (2.0, v1.2.0), a git SHA, a duration (31.8s), a task-id (A.1), or
# arbitrary backtick content — those name no file and were the completion gate's measured
# false-positive source (5.83% irreducible on the 1200-msg honest corpus). A backticked
# path still matches: the path token is found wherever it sits, backticks or not.
# Well-known extensionless files that ARE locations (so "created the Dockerfile" binds).
_DOTLESS_FILES = r"Makefile|Dockerfile|README|LICENSE|CHANGELOG|Gemfile|Procfile|CODEOWNERS"
_LOC_RX = re.compile(
    r"(?<![\w])"                                                     # left boundary
    r"(?:"
    r"(?:/|~/|\./|\.\./)?(?:[\w.\-]+/)*[\w.\-]+\.(?:" + _PATH_EXT + r")"  # path + known ext
    r"|(?:" + _DOTLESS_FILES + r")"                                  # known extensionless file
    r")"
    r"(?![\w])",                                                     # right boundary (ext not extended)
    re.IGNORECASE,
)
def detect_locations(text: str):
    """Yield (location, start, end) for every located file path in `text`, in order.

    Used by the completion gate to bind a production claim to the right path when a
    message names several (the producing verb may govern the second, not the first)."""
    for m in _LOC_RX.finditer(text or ""):
        yield (m.group(0), m.start(), m.end())


# ---- tool/event I/O parsing --------------------------------------------------------------------
# Knight-Leveson: stdlib only (json, regex). No HTTP, no LLM, no DuckDB. Consumed by the
# history-walking predicate (content.fabricated_commit_sha), the ledger, and the Stop
# green-claim gate.

def _raw_payload(row):
    """The raw payload cell of a history row, across both shapes: the events-table
    (id, ts, event_type, cwd, payload_json) tuple carries it at index 4, a dict-like carries it
    under 'payload'. Unknown shape -> None (falsy, exactly like an absent payload).

    Shared by `raw_payload_str` and `decode_history_row` so the two can never drift on
    what counts as a payload cell.
    """
    if isinstance(row, (tuple, list)) and len(row) > 4:
        return row[4]
    if hasattr(row, "get"):
        return row.get("payload")
    return None


def raw_payload_str(entry) -> str:
    """history row -> the raw payload JSON string ('' for anything undecodable).

    events-table rows are 5-tuples (id, ts, event_type, cwd, payload_json); some callers pass
    dict-likes with a 'payload' key. Exposed for callers that need the raw string itself
    (content.fabricated_commit_sha's grounded-SHA substring scan).
    """
    raw = _raw_payload(entry)
    return raw if isinstance(raw, str) else ""


def decode_history_row(row):
    """Decode one history row's raw JSON payload into an event dict, or None if the row is
    malformed/absent/unparseable. Rows are either the (id, ts, event_type, cwd, raw_payload_json)
    5-tuples the events table returns, or dict-likes carrying a 'payload' key (corpus replay).
    Fail-open: an undecodable row yields None rather than raising, so one malformed row can never
    crash a caller's scan.

    The ONE canonical row-decode step. Callers keep their own downstream shape/filter (a Call
    dict, a (name, command, response) tuple, a ByteIdentity list) -- only the shared
    decode-to-dict step lives here."""
    raw = _raw_payload(row)
    if not raw:
        return None
    try:
        decoded = raw if isinstance(raw, dict) else json.loads(raw)
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def decode_history_event(row):
    """Like `decode_history_row`, but also backfills `hook_event_name` from the row's own
    WRAPPER event-type column (tuple index 2, or dict key `event_type`) when the payload itself
    doesn't carry one -- the canonical merge of `decode_history_row` + the wrapper-etype
    fallback.

    A payload whose event type lives solely on the wrapper column would otherwise decode with no
    `hook_event_name`, and `event.identical_retry` requires an exact `== "PostToolUse"` match --
    so it would go silently blind to rows `canon.timeout`/`canon.recur` act on, from the same
    table, for the same concept."""
    wrapper_etype = _event_type_of(row)   # '' (falsy) when the row carries no wrapper column
    ev = decode_history_row(row)
    if ev is None:
        return None
    if not ev.get("hook_event_name") and wrapper_etype:
        ev = {**ev, "hook_event_name": wrapper_etype}
    return ev


def failure_terminal_result(ev) -> dict:
    """Normalize a PostToolUseFailure event to the shared result-dict shape.

    The shape is always ``{"error": <non-empty str>, "interrupted": <bool>}``.  A terminal
    whose optional error detail is absent gets the deliberately generic ``"tool call failed"``
    fallback: the event type is itself evidence that the call failed, but generic wording stays
    unclassified by :func:`classify_failure` and therefore cannot invent a deterministic retry
    block.  Keeping this normalization here prevents history decoders from drifting on whether a
    missing error means failure, success, or uncertainty.
    """
    event = ev if isinstance(ev, dict) else {}
    error = event.get("error")
    return {
        "error": str(error) if error else "tool call failed",
        "interrupted": bool(event.get("is_interrupt")),
    }


def bash_output_text(tool_response) -> str:
    """extract captured stdout+stderr from a Bash tool_response.

    PRODUCTION SHAPE (verified vs the real makoto events DB): Bash PostToolUse
    tool_response is a DICT with keys stdout/stderr/interrupted/isImage/
    noOutputExpected. We pull stdout and stderr. str / list are tolerated for the
    synthetic-test payload shape. Shared by the ledger (records Bash result rows)."""
    if isinstance(tool_response, dict):
        out = tool_response.get("stdout", "") or ""
        err = tool_response.get("stderr", "") or ""
        return f"{out}\n{err}"
    if isinstance(tool_response, list):
        return " ".join(
            str(b.get("text", b) if isinstance(b, dict) else b) for b in tool_response
        )
    if isinstance(tool_response, str):
        return tool_response
    return ""


def is_failing_testrun(output: str) -> bool:
    """True iff `output` (recorded test-runner stdout+stderr) shows >=1 REAL failure or error.
    xfail-safe and 0-failed-safe by construction; a clean or expected-fail run is False.

    ANSI SGR codes are stripped first: vitest/jest colorize the summary, and the SGR terminator 'm'
    abuts the count ('\\x1b[31m2 failed'), which would otherwise kill the \\b before `[1-9]\\d* failed`
    and let a real failing run read as green (measured: 18 such misses on the honest corpus)."""
    if not output:
        return False
    output = _ANSI_SGR_RX.sub("", output)
    return bool(_FAILURE_SUMMARY_RX.search(output) or _FAILURE_MARKER_RX.search(output))


def is_test_runner(command: str) -> bool:
    """True iff a Bash command invokes a recognized test runner (open-world; unlisted -> recall bound)."""
    return bool(command) and _command_runs_tests(command)


def iter_tool_events(history):
    """Yield (tool_name, command, response_text) per prior tool event in `history`. Rows are the
    (id, ts, event_type, cwd, raw_payload_json) tuples dispatch._select_recent returns, OR dicts
    with a 'payload' key (the shape measure_corpus_fp builds). The faithful events-table source
    (full command + full tool_response, like predicate content.unsourced_webfetch) — NOT the lossy
    ledger. Fail-open: an unparseable row is skipped, so a malformed event can never crash a Stop
    gate.

    Tolerates dict payloads (raw if isinstance(raw, dict)), deliberately MORE permissive than the
    str-only raw_payload_str path. Decode step delegates to decode_history_row, so parsed JSON
    with the wrong envelope shape is skipped there just like invalid JSON."""
    for row in history or ():
        ev = decode_history_row(row)
        if ev is None:
            continue
        ti = ev.get("tool_input", {}) or {}
        tr = ev.get("tool_response", {})
        if isinstance(tr, str):
            resp = tr
        elif isinstance(tr, dict):
            resp = " ".join(str(tr.get(k, "") or "") for k in ("stdout", "stderr", "output"))
        else:
            resp = ""
        yield (ev.get("tool_name", ""), ti.get("command", "") or "", resp.strip())


# ---- predicate factories + AST primitives -------------------------------------------------------
# regex_file_predicate / ast_introduced_predicate build the PreToolUse content-scan predicate
# scaffold; scan_target_content / parse_introduced / is_false_const / is_cert_none / callee_chain /
# makoto_allowed are their shared leaves.

def makoto_allowed(content: str) -> bool:
    """True iff the content carries a structured `makoto-allow: <reason>` exemption marker
    (colon + a non-empty reason). A bare `makoto-allow` does not exempt — §7.5b."""
    return bool(content) and _MAKOTO_ALLOW_RX.search(content) is not None


def makoto_allow_reason(content: str) -> Optional[str]:
    """The rationale text of a `makoto-allow: <reason>` marker, for the on-record exemption row.
    Trailing comment-close tokens (-->, */, #}, }}) and whitespace are trimmed; capped at 200
    chars so one row stays well under the PIPE_BUF append-atomicity bound. None when no marker."""
    m = _MAKOTO_ALLOW_REASON_RX.search(content or "")
    if not m:
        return None
    reason = m.group(1).strip()
    for close in ("-->", "*/", "#}", "}}", "--%>"):
        idx = reason.find(close)
        if idx != -1:
            reason = reason[:idx].strip()
    return reason[:200]


# Exemption recording is an UPWARD concern (it writes to the audit layer), so this L1 leaf must not
# reach for it. Instead it exposes a SINK the L3 orchestrator injects (dependency inversion): a
# pure unit call with no sink installed returns None on an exempted match, unchanged. The
# dispatcher wires the audit-writing sink at import, so the detector never grows an audit
# dependency.
_EXEMPTION_SINK: Optional[Callable[..., None]] = None


def set_exemption_sink(fn: Optional[Callable[..., None]]) -> None:
    """Install (or clear, with None) the callback the predicates invoke when a makoto-allow marker
    suppresses a CONFIRMED match. Injected by makoto.dispatch; absent in pure unit calls."""
    global _EXEMPTION_SINK
    _EXEMPTION_SINK = fn


def _record_exemption(current_event: dict, conn, *, pattern_id: str, file: str,
                      line: int, reason: str, snippet: str) -> None:
    """Forward a suppressed-match record to the injected sink (no-op when none is installed). Keeps
    the escape valve open but no longer silent; fail-safe — recording must never break the allow path."""
    sink = _EXEMPTION_SINK
    if sink is None:
        return
    try:
        sink(current_event=current_event, conn=conn, pattern_id=pattern_id, kind="makoto-allow",
             file=file, line=line, reason=reason, snippet=snippet)
    except Exception:
        pass


def _gated_content(*, current_event: dict, target_rx: re.Pattern,
                    exempt_rx: Optional[re.Pattern]) -> Optional[tuple]:
    """Shared gate scaffold of both content-scan factories below: PreToolUse-only, `target_rx`
    gates `file_path`, `exempt_rx` gates content. Returns `(fp, content)` to continue, or None to
    stay silent (mirrors each predicate's own "no opinion" return)."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    ti = current_event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "")
    if not target_rx.search(fp):
        return None
    content = scan_target_content(ti)
    if exempt_rx is not None and exempt_rx.search(content):
        return None  # documented code-level carve-out (e.g. an ADR backlink) -> silent
    return fp, content


def _exempt_or_finding(*, current_event: dict, conn, pattern: Check, fp: str, line_no: int,
                       snippet: str, content: str, message: str) -> Optional[Finding]:
    """Shared tail of both content-scan factories below: DETECT-THEN-EXEMPT -- record a
    suppressed match rather than silently drop it (R5b), else build the real Finding."""
    if makoto_allowed(content):
        _record_exemption(current_event, conn, pattern_id=pattern.id, file=fp,
                          line=line_no, reason=makoto_allow_reason(content) or "",
                          snippet=snippet)
        return None  # AI documented this instance as legitimate (see CLAUDE.md) — recorded
    return Finding(
        # Pre-tier checks are invariantly posture=BLOCK (tests/test_pre_tier_block_invariant.py).
        # Finding.level's vocabulary ("error"/"advisory") is a separate axis from posture's
        # ("BLOCK"/"ADVISE"/...), so this is a literal, not a `pattern.posture` passthrough.
        pattern_id=pattern.id, file=fp, line=line_no, level="error",
        message=message, retry_hint=pattern.retry_hint, snippet=snippet,
    )


def scan_target_content(tool_input: dict) -> str:
    """The NEW text a PreToolUse file-mutation introduces, for content-scan patterns.

    Write exposes the full new file as ``content``; Edit exposes its replacement as
    ``new_string``; MultiEdit exposes a list of ``{old_string, new_string}`` edits. We
    return the text being INTRODUCED (never ``old_string``), so an AI cannot weaken a
    verifier via Edit/MultiEdit and evade the content-scan patterns (e.g. inserting
    `.startswith(` into a verifier via Edit to slip past content.verifier_predicate_weakened).
    Scanning only the introduced text (not the whole post-edit file) keeps Edit FP-safe:
    a pattern fires solely on a shape the AI is actively adding.
    """
    if not isinstance(tool_input, dict):
        return ""
    content = tool_input.get("content")
    if content:
        return content
    new_string = tool_input.get("new_string")
    if new_string:
        return new_string
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        return "\n".join(e.get("new_string", "") for e in edits
                         if isinstance(e, dict) and e.get("new_string"))
    return ""


def introduced_text(tool_name: str, tool_input: dict) -> str:
    """The text a PreToolUse call would introduce, across every tool that can carry it: a
    Bash `command` verbatim, or the Write/Edit/MultiEdit new content (`scan_target_content`).
    Shared by every "would this call INTRODUCE a flagged string" predicate
    (content.illusory_authorship_trailer, content.illusory_interruption_claim, ...)."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""
    if tool_name == "NotebookEdit":
        # NotebookEdit carries its new cell text under `new_source`, not `content`/`new_string`
        # -- without this branch a flagged string introduced via a notebook cell read as clean.
        return tool_input.get("new_source", "") or ""
    return scan_target_content(tool_input)


def parse_introduced(content: str):
    """Parse INTRODUCED text into an AST module, fragment-tolerant — the "only active
    code" gate's substrate.

    Returns ``(tree, line_offset)``; ``(None, 0)`` when the text cannot be parsed as
    Python. An unparseable fragment is NEVER confirmed as active code, so AST predicates
    built on this degrade to SILENT (FN-safe) rather than firing on a comment / string /
    docstring MENTION — collapsing the mention-vs-instance FP class the regex patterns
    can only exempt. ``line_offset`` is subtracted from a node's ``lineno`` to recover the
    1-indexed line within ``content`` (1 when the ``if True:`` wrapper was needed, else 0).

    Edit ``new_string`` payloads are often an indented STATEMENT fragment; we ``dedent``
    then, on failure, wrap in ``if True:`` so a bare indented statement still parses. A
    fragment that is not a whole statement (e.g. ``", verify=False)``) parses under
    neither and stays silent.
    """
    if not content or not content.strip():
        return None, 0
    dedented = textwrap.dedent(content)
    try:
        return ast.parse(dedented), 0
    except (SyntaxError, ValueError):
        pass
    try:
        body = "\n".join("    " + ln for ln in dedented.splitlines())
        return ast.parse("if True:\n" + body), 1
    except (SyntaxError, ValueError):
        return None, 0


def is_false_const(node) -> bool:
    """True iff `node` is the literal ``False`` constant (an AST Constant whose value IS False).
    Shared by the ``verify=False`` / ``check_hostname=False`` keyword detectors (content.cert_verify_disabled TLS, content.jwt_signature_disabled JWT)."""
    return isinstance(node, ast.Constant) and node.value is False


def is_cert_none(node) -> bool:
    """True iff `node` is ``ssl.CERT_NONE`` (Attribute) or a bare ``CERT_NONE`` Name. Shared by the
    cert-disable detectors: content.cert_none_mode (``verify_mode = CERT_NONE`` assign) and content.cert_reqs_none (``cert_reqs=CERT_NONE`` kwarg)."""
    if isinstance(node, ast.Attribute) and node.attr == "CERT_NONE":
        return True
    return isinstance(node, ast.Name) and node.id == "CERT_NONE"


def callee_chain(call: ast.Call) -> str:
    """Dotted callee name of a Call — ``requests.get``, ``jwt.decode``, ``jose.jwt.decode``.
    Descends through an intermediate Call so ``requests.Session().get(...)`` / ``jwt.JWT().decode(...)``
    keep the receiver token (else the chain would stop at ``.get`` / ``.decode`` and miss the library).
    Shared by the library-callee-gated detectors (content.cert_verify_disabled TLS, content.jwt_signature_disabled JWT)."""
    parts: list = []
    f = call.func
    while True:
        if isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        elif isinstance(f, ast.Call):
            f = f.func                       # `X().<m>` -> keep walking X
        elif isinstance(f, ast.Name):
            parts.append(f.id)
            break
        else:
            break
    return ".".join(reversed(parts))


def jwt_decode_callee_chain(node) -> Optional[str]:
    """The callee-chain string iff `node` is an `ast.Call` targeting a jwt/jose `decode` entry
    point (JWT_CALLEE_RX matches the chain, AND the chain's tail is literally `decode`); None
    otherwise. Shared callee gate for content.jwt_signature_disabled (verify=False /
    options-dict disable) and content.jwt_none_alg (algorithms=["none"] whitelisting) — both
    patterns need this SAME 'is this really a jwt.decode(...) call' precondition before
    inspecting their own distinct keyword."""
    if not isinstance(node, ast.Call):
        return None
    chain = callee_chain(node)
    if not JWT_CALLEE_RX.search(chain):
        return None
    if chain.split(".")[-1] != "decode":
        return None
    return chain


def canon_input(inp) -> str:
    """A stable, identity-comparable serialization of a tool_input (key order-independent).
    Compares two calls for byte-identity only; reads no content semantically. ONE owner:
    canon.timeout/recur and identicalRetryInterdiction pair calls by the same fold."""
    try:
        return json.dumps(inp, sort_keys=True, default=str)
    except Exception:
        return repr(inp)


def ast_introduced_predicate(
    *,
    target_rx: re.Pattern,
    node_match: Callable[[ast.AST], Optional[str]],
    exempt_rx: Optional[re.Pattern] = None,
    exempt_label: str = "",
    parse: Callable[[str], tuple] = None,
) -> Callable[..., Optional[Finding]]:
    """Build a PreToolUse content-scan predicate that fires ONLY on a real AST node in the
    INTRODUCED code — the "only active code" companion to :func:`regex_file_predicate`.

    Shares the gate / file-path / ``makoto_allowed`` / introduced-text scaffold, then parses
    the introduced text (``parse_introduced``) and walks it; ``node_match(node)`` returns a
    short label string on a match, else ``None``/falsy. Because matching is on real AST nodes,
    a comment, a ``str`` Constant (string literal / docstring), or a doc mention can never
    match — that is what makes a fire MATERIAL rather than illusory.

    Args mirror :func:`regex_file_predicate` (``target_rx`` gates ``file_path``; the optional
    ``exempt_rx``/``exempt_label`` give the documented-carve-out + message suffix).
    """
    suffix = f" with no {exempt_label}" if exempt_label else ""

    def _predicate(*, current_event: dict, history: list,
                   pattern: Check, conn=None) -> Optional[Finding]:
        gated = _gated_content(current_event=current_event, target_rx=target_rx, exempt_rx=exempt_rx)
        if gated is None:
            return None
        fp, content = gated
        tree, off = (parse or parse_introduced)(content)
        if tree is None:
            return None  # unparseable fragment -> not confirmed active -> silent (FN-safe)
        for node in ast.walk(tree):
            label = node_match(node)
            if not label:
                continue
            line_no = max(1, getattr(node, "lineno", 1) - off)
            lines = content.splitlines()
            snippet = lines[line_no - 1].strip()[:120] if 0 < line_no <= len(lines) else str(label)
            return _exempt_or_finding(
                current_event=current_event, conn=conn, pattern=pattern, fp=fp, line_no=line_no,
                snippet=snippet, content=content,
                message=f"row {pattern.id} ({pattern.description}): active-code match {label!r} "
                        f"at line {line_no}{suffix}")
        return None

    return _predicate


def regex_file_predicate(
    *,
    target_rx: re.Pattern,
    body_rx: re.Pattern,
    exempt_rx: Optional[re.Pattern] = None,
    exempt_label: str = "",
) -> Callable[..., Optional[Finding]]:
    """build a PreToolUse Write/Edit content-scan predicate from two regexes.

    Args:
      target_rx:    matched against `tool_input.file_path`; gate (None if no match)
      body_rx:      matched against `tool_input.content`; fires Finding on first hit
      exempt_rx:    optional SECOND exemption (beyond the universal makoto_allowed) — when it
                    matches the content, the predicate stays silent (e.g. an `ADR-NNN` backlink
                    exempts the finding).
      exempt_label: human label for exempt_rx; when set, a firing message gets the
                    ` with no <label>` suffix.

    Returns:
      A predicate(*, current_event, history, pattern, conn) -> Optional[Finding]
      with the shared gate/exempt/match/line/snippet/Finding scaffold.
    """
    suffix = f" with no {exempt_label}" if exempt_label else ""

    def _predicate(*, current_event: dict, history: list,
                   pattern: Check, conn=None) -> Optional[Finding]:
        gated = _gated_content(current_event=current_event, target_rx=target_rx, exempt_rx=exempt_rx)
        if gated is None:
            return None
        fp, content = gated
        m = body_rx.search(content)
        if not m:
            return None
        line_no = content[: m.start()].count("\n") + 1
        snippet = content[max(0, m.start() - 40): m.end() + 40]
        return _exempt_or_finding(
            current_event=current_event, conn=conn, pattern=pattern, fp=fp, line_no=line_no,
            snippet=snippet, content=content,
            message=f"row {pattern.id} ({pattern.description}): matched {m.group(0)!r} at line {line_no}{suffix}")
    return _predicate


def unwitnessed(events, *, owes, pays, paid=()):
    """The one shape: an event owes a witness, and only an earlier event can pay it.

    `owes(ev)` gives the subjects `ev` commits to; `pays(ev)` gives a predicate over subjects
    that `ev` witnesses, or None. Yields `(ev, subject)` for every subject nothing up to it
    paid. `paid` seeds predicates that hold before the first event, for a caller whose witness
    is the whole record rather than one event of it. A witness pays its own event and every
    later one, never an earlier one. One pass; a predicate that pays everything
    short-circuits, so an obligation stays O(events).

    The register's families differ only in what counts as the witness: none can pay a held
    wrong form (SPEC), a second reading of the subject (THE OTHER POINT), an act that selected
    the branch (THE SWITCH), a read of the source before the write (THE LINEAGE).
    """
    paid = list(paid)
    for ev in events:
        p = pays(ev)
        if p is not None:
            paid.append(p)
        for subject in owes(ev) or ():
            if not any(q(subject) for q in paid):
                yield ev, subject


def claim_vs_history_predicate(
    *, claim_rxs, neg_ref_rx, grounded_in_history, tool_gate, message,
) -> Callable[..., Optional[Finding]]:
    """Build a claim-vs-recorded-history Pre predicate.

    ``claim_rxs`` is normally a tuple of compiled regexes.  A callable extractor is also
    accepted for checks whose established claim grammar needs clause-aware negation handling.
    An empty tuple means the subject returned by ``tool_gate`` is itself the claim.
    """
    def _predicate(*, current_event: dict, history: list,
                   pattern: Check, conn=None) -> Optional[Finding]:
        subject = tool_gate(current_event)
        if subject is None:
            return None
        if callable(claim_rxs):
            claims = claim_rxs(subject)
        elif not claim_rxs:
            claims = (subject,)
        else:
            claims = []
            for rx in claim_rxs:
                for match in rx.finditer(subject):
                    if neg_ref_rx and neg_ref_rx.search(
                        subject[max(0, match.start() - 80):match.end() + 40]
                    ):
                        continue
                    # `lastindex`, not `groups()`: "the regex HAS groups" is not "group 1
                    # matched" — a non-participating optional group yielded claims=[None].
                    claims.append(match.group(1) if match.lastindex else match.group(0))
        for _ev, claimed in unwitnessed(
                (subject,), owes=lambda _s: claims, pays=lambda _s: None,
                paid=(lambda c: grounded_in_history(c, history),)):
            rendered = message(claimed, subject, pattern) if callable(message) else message.format(
                claimed=claimed, id=pattern.id, description=pattern.description
            )
            return Finding(
                pattern_id=pattern.id, file="", line=0, level="error", message=rendered,
                retry_hint=pattern.retry_hint, snippet=str(claimed if not subject else subject)[:200],
            )
        return None
    return _predicate


# The fields a GitHub MCP call publishes as text. Without them a PR body or comment carrying an
# attribution footer read as clean. Search `query` strings are left out, so an audit that
# searches for the footer is not refused for naming it.
_PUBLISHED_KEYS = ("title", "body", "message", "commit_title", "commit_message")


def published_text(tool_name: str, tool_input: dict) -> str:
    """The text a GitHub MCP call would publish: its body/title/message fields and every
    `files[].content` of a push_files."""
    if not tool_name.startswith("mcp__github__") or not isinstance(tool_input, dict):
        return ""
    parts = [tool_input[k] for k in _PUBLISHED_KEYS if isinstance(tool_input.get(k), str)]
    files = tool_input.get("files")
    if isinstance(files, list):
        parts += [f["content"] for f in files
                  if isinstance(f, dict) and isinstance(f.get("content"), str)]
    return "\n".join(parts)


def _introduced_regex_scan(current_event: dict, body_rx: re.Pattern):
    """Shared scan step behind `introduced_regex_predicate`: scan ANY tool's INTRODUCED text (via
    `introduced_text` — Write/Edit/MultiEdit content OR a Bash command, not just a file-path-gated
    Write/Edit body the way `regex_file_predicate`'s `target_rx` requires) for `body_rx`. Returns
    None (no finding) or a (match, text, tool_input, tool_name) tuple for the caller to finish
    building a Finding from.
    """
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = current_event.get("tool_name", "") or ""
    tool_input = current_event.get("tool_input", {}) or {}
    text = "\n".join(t for t in (introduced_text(tool_name, tool_input),
                                  published_text(tool_name, tool_input)) if t)
    if not text:
        return None
    m = body_rx.search(text)
    if not m:
        return None
    return m, text, tool_input, tool_name


def _introduced_regex_finding(pattern: Check, m, text: str, tool_input: dict, tool_name: str,
                               suffix: str = "") -> Finding:
    line_no = text[: m.start()].count("\n") + 1
    snippet = text[max(0, m.start() - 40): m.end() + 40].strip()
    where = tool_input.get("file_path", "") or f"{tool_name or 'tool'} command"
    return Finding(
        pattern_id=pattern.id, file=where, line=line_no, level="error",
        message=f"row {pattern.id} ({pattern.description}): matched {m.group(0)!r} at line {line_no}{suffix}",
        retry_hint=pattern.retry_hint, snippet=snippet,
    )


def introduced_regex_predicate(
    *, body_rx: re.Pattern, grounded_in_history=None, veto_suffix: str = "",
) -> Callable[..., Optional[Finding]]:
    """Build a Pre predicate over `_introduced_regex_scan` + `_introduced_regex_finding`. With no
    `grounded_in_history` it is a SPEC row (the pattern is the whole definition); with one, a real
    instance of the claim on the record is its witness, paid through `unwitnessed`, and the finding
    is suppressed. tests/test_check_law_tests.py reads which from the call's own keywords.
    """
    def _predicate(*, current_event: dict, history: list,
                   pattern: Check, conn=None) -> Optional[Finding]:
        hit = _introduced_regex_scan(current_event, body_rx)
        if hit is None:
            return None
        m, text, tool_input, tool_name = hit
        if makoto_allowed(text):
            # DETECT-THEN-EXEMPT (R5b), matching `_exempt_or_finding`: the match is real, the
            # marker suppresses the Finding, and the suppression is RECORDED (not silently dropped).
            line_no = text[: m.start()].count("\n") + 1
            _record_exemption(
                current_event, conn, pattern_id=pattern.id,
                file=tool_input.get("file_path", "") or f"{tool_name or 'tool'} command",
                line=line_no, reason=makoto_allow_reason(text) or "",
                snippet=text[max(0, m.start() - 40): m.end() + 40].strip())
            return None  # universal exemption: AI documented this as legitimate (see CLAUDE.md)
        if grounded_in_history is None:
            return _introduced_regex_finding(pattern, m, text, tool_input, tool_name)
        for _ev, _m in unwitnessed((m,), owes=lambda mm: (mm,), pays=lambda _mm: None,
                                   paid=(lambda _mm: grounded_in_history(history),)):
            return _introduced_regex_finding(pattern, m, text, tool_input, tool_name, veto_suffix)
        return None  # a real instance IS on the record -- the claim is grounded, not illusory
    return _predicate


def response_text(ev: dict) -> str:
    """The text a settled tool call PRINTED, from one decoded event. The obligation gates need
    this beside `tool_input`, which `iter_tool_events` drops -- same normalization that iterator
    applies to `tool_response` (stdout + stderr + output joined, a bare string taken as-is), kept
    here as ONE definition rather than re-derived per gate. Empty string for anything else, so a
    caller never has to test the shape."""
    tr = ev.get("tool_response")
    if isinstance(tr, str):
        return tr.strip()
    if isinstance(tr, dict):
        return " ".join(str(tr.get(k, "") or "") for k in ("stdout", "stderr", "output")).strip()
    return ""


def command_of(ev: dict) -> str:
    """The Bash command a decoded event carries, or "" -- one definition, for the same reason."""
    ti = ev.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    return str(ti.get("command", "") or "")


def command_matches(rx: re.Pattern):
    """An act/guard predicate for `unmet_obligation_gate`: this event's Bash command matches `rx`.

    Shared to avoid duplicate copies across the obligation gates. A gate that needs more than
    "the command matches" still writes its own predicate (`unreadStructure` reads the RESPONSE
    too, `unobservedDestruction` splits shell segments).
    """
    def _predicate(ev: dict) -> bool:
        cmd = command_of(ev)
        return bool(cmd and rx.search(cmd))
    return _predicate


# A verifier RAN in this event, whatever it reported. ONE definition, shared by every obligation
# whose guard is "something observed behaviour": `gate.unobserved_destruction` and
# `gate.relaunched_unchanged` both mean exactly this. The verdict is deliberately not read: a
# report either way is the observation, and only the absence of both leaves the act resting on
# nothing. Spelled as a `command_matches` application rather than its own def, because a def
# with that body would be alpha-equivalent to the factory's.
ran_a_verifier = command_matches(_TEST_RUNNER_RX)


def unmet_obligation_gate(*, act, guard, message, retry_hint, pattern_id,
                          level="advisory", min_acts=1) -> Callable[..., Optional[Finding]]:
    """Build a Stop-edge OBLIGATION gate: a costly act ran this session and no qualifying guard
    preceded it.

    Every other check in this catalog holds the assistant's STATEMENT against the record. An
    obligation holds an ACT against a guard that had to come first: no statement is needed and
    none is read, so a turn that says nothing at all can still owe.

    `act` and `guard` are predicates over ONE decoded history event -- the full dict, not
    `iter_tool_events`' (name, command, response) triple, so a caller can read the `tool_input`
    keys that triple drops. ORDER IS THE WHOLE CHECK: a guard seen before the act pays it for
    the rest of the session, and a guard seen after does not, because the act already ran on
    unknown ground. `min_acts` fires only from the Nth unguarded act onward, for a clause whose
    costly thing is the REPEAT rather than the first one.

    One O(history) pass and no store: the obligation is a pure function of the event sequence,
    so it cannot go stale and has no write path to get wrong; a derived obligation needs
    neither a table nor a reconcile.

    NAMED RECALL BOUND: history is `_select_recent`'s rolling window, so an act older than the
    window reads as never having happened. Same bound `claimedRunningAbsent` documents for its
    own evidence, and it fails OPEN -- the gate goes quiet, never louder.
    """
    def _run(history) -> Optional[Finding]:
        # fail open: an undecodable row could be the guard, so it is skipped, never an act
        events = (ev for ev in map(decode_history_event, history or ()) if isinstance(ev, dict))
        unpaid = [ev for ev, _ in unwitnessed(
            events, owes=lambda ev: (ev,) if act(ev) else (),
            pays=lambda ev: (lambda _s: True) if guard(ev) else None)]
        if len(unpaid) < min_acts:
            return None
        offender = unpaid[-1]
        return Finding(
            pattern_id=pattern_id, file="", line=0, level=level,
            message=message, retry_hint=retry_hint,
            snippet=str(offender.get("tool_name", ""))[:200],
        )
    return _run


def live_query_finding(*, query, posture_label) -> Callable[..., Optional[Finding]]:
    """Build a Stop check whose live query result is itself the evidence."""
    input_name = query.__code__.co_varnames[0] if query.__code__.co_argcount else ""
    if input_name == "plan":
        def _check(c):
            result = query(c.plan)
            if result is None or isinstance(result, Finding):
                return result
            return Finding(pattern_id=posture_label, file="", line=0, level="advisory",
                           message=f"{posture_label}: {result}")
    elif input_name == "fs_read":
        def _check(c):
            result = query(c.fs_read)
            if result is None or isinstance(result, Finding):
                return result
            return Finding(pattern_id=posture_label, file="", line=0, level="advisory",
                           message=f"{posture_label}: {result}")
    else:
        raise TypeError("live query parameter must be named 'plan' or 'fs_read'")
    _check.__module__ = query.__module__
    return _check


# ---- transient-vs-deterministic failure classification -------------------------------------------
# A BLOCK-tier check denying a retry must never deny a LEGITIMATE re-poll of a transient failure
# (a timeout, a 5xx, "still running"), so this classifier is conservative -- it fails toward
# UNCERTAIN (None), never toward "assume deterministic", whenever the signal is ambiguous.
# identicalRetryInterdiction.py refuses to fire on anything but a confident True.

# Markers whose PRESENCE means the failure will NOT change on an UNMODIFIED retry -- the error is
# a property of the call itself (a typo, a missing module, a permission the environment will not
# grant merely by waiting), not of external timing/state. Each is a real, specific runtime-error
# shape, not a vague "sounds bad" heuristic.
_DETERMINISTIC_MARKERS = (
    re.compile(r"SyntaxError", re.IGNORECASE),
    re.compile(r"No such file or directory"),
    re.compile(r"Permission denied"),
    re.compile(r"ModuleNotFoundError|ImportError"),
    re.compile(r"command not found"),
    re.compile(r"is not recognized as an internal or external command"),
    re.compile(r"NameError|AttributeError"),
)

# Markers whose PRESENCE means the failure is plausibly time/external-state dependent -- a retry
# after a real wait, or once a dependency recovers, is a legitimately DIFFERENT action even with
# byte-identical input. Presence of either class wins its own side; presence of BOTH is ambiguous
# (fails to None, never guessed).
_TRANSIENT_MARKERS = (
    re.compile(r"\bconnection (?:refused|error|reset|closed|aborted)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:ECONNRESET|ECONNREFUSED|ECONNABORTED|EAI_AGAIN|EHOSTUNREACH|ENETUNREACH|EPIPE)\b",
        re.IGNORECASE),
    re.compile(r"\bnetwork (?:error|is unreachable)\b", re.IGNORECASE),
    re.compile(r"\bfetch failed\b", re.IGNORECASE),
    re.compile(r"\btimed? ?out\b", re.IGNORECASE),
    re.compile(r"Temporary failure in name resolution"),
    re.compile(r"\b(?:502|503|504)\b"),
    re.compile(r"\b429\b"),
    re.compile(r"rate limit", re.IGNORECASE),
    re.compile(r"try again", re.IGNORECASE),
    re.compile(r"still (?:running|pending|in progress)", re.IGNORECASE),
)


def classify_failure(text: str) -> Optional[bool]:
    """True = deterministic (an unmodified retry cannot help); False = transient (a retry might
    legitimately help); None = UNCERTAIN -- neither class matched, or both did. None is the safe
    default a BLOCK-tier caller must treat as "do not fire", never as a coin flip."""
    if not text:
        return None
    det = any(rx.search(text) for rx in _DETERMINISTIC_MARKERS)
    trans = any(rx.search(text) for rx in _TRANSIENT_MARKERS)
    if det and not trans:
        return True
    if trans and not det:
        return False
    return None


# ---- test-delta redirect -------------------------------------------------------------------------
# Wired DIRECTLY into `dispatch.py`'s PostToolUse branch, not the patterns.toml/load_prechecks
# catalog (Pre-only) nor the Stop-gate catalog (Stop-only) -- neither covers a Post-edge advisory.
#
# `compute_delta` reuses `namedTestTeeth.py`'s OWN `recorded_failed_names`/`recorded_passed_names`
# parsers (one implementation, never a second one) to diff the per-test verdict set between the
# PRIOR recorded testrun output and the NEW one just produced. The import is call-time so this
# kit module never carries an import-time edge into a named check module.

def current_named_verdicts(history) -> dict:
    """{full_test_id: 'FAIL'|'PASS'} from the recorded TEST-RUNNER outputs in `history`, in
    order. The key is the exact recorded id — `path::name[param]` — matching the header's
    "exact test id" pin (a bare-name key let tests/a's failure shadow tests/b's same-named
    test, and let one parametrized case discharge another). Only responses of a recognized
    test-runner invocation are read (`kit.is_test_runner` on the recorded command): a FAILED
    line the agent merely DISPLAYED — `cat old.log` — is not a run and must never ground a
    DENY. Within one response, records apply in TEXTUAL ORDER and the last verdict wins (a
    run-fix-rerun sequence captured in one Bash call ends on its true final verdict), exactly
    as the last verdict wins across responses (a fix-and-rerun-green discharges an earlier
    red; a re-fail re-opens). ANSI is stripped first (vitest/jest colorize verdict lines). A
    verdict recorded inside mutation/teeth framing is not material — scoped to the
    record's own vicinity (`_TEETH_SCOPE_*`), never the whole response, and applied
    SYMMETRICALLY: a framed FAILED is no material failure, and a framed PASSED (a pass under
    deliberately-induced-failure framing is evidence the test cannot fail) is no material
    discharge either."""
    verdict = {}
    for _tool, cmd, resp in iter_tool_events(history):
        if not resp or not is_test_runner(cmd or ""):
            continue
        resp = _ANSI_SGR_RX.sub("", resp)
        # Short-circuit through the shared per-name parsers (the same evidence primitives
        # kit.compute_delta reuses) before the positioned scan below: most runner responses
        # carry no per-test verdict lines at all.
        if not (recorded_failed_names(resp) or recorded_passed_names(resp)):
            continue
        records = []
        for rx, v in ((_REC_FAIL_LEAD_RX, "FAIL"), (_REC_FAIL_TRAIL_RX, "FAIL"),
                      (_REC_PASS_LEAD_RX, "PASS"), (_REC_PASS_TRAIL_RX, "PASS")):
            for m in rx.finditer(resp):
                records.append(
                    (m.start(), m.end(), f'{m.group("path")}::{m.group("name")}', v))
        for start, end, tid, v in sorted(records):
            window = resp[max(0, start - _TEETH_SCOPE_BEFORE):end + _TEETH_SCOPE_AFTER]
            if _TEETH_FRAME_RX.search(window):
                continue                              # deliberately-induced -> not material
            verdict[tid] = v
    return verdict


def compute_delta(prior_output: str, new_output: str) -> Optional[str]:
    """None when there's nothing to say: no prior run to diff against, or no verdict flipped.
    "Newly failing" = named tests failing now that were NOT already failing in the prior run;
    "newly passing" = named tests passing now that WERE failing in the prior run (a genuine
    fix). A test that was already failing and is STILL failing is neither -- not new information,
    so it stays out of the delta (grounding on what CHANGED, not the whole persistent state)."""
    if not prior_output or not new_output:
        return None
    prior_failed = recorded_failed_names(prior_output)
    new_failed = recorded_failed_names(new_output)
    new_passed = recorded_passed_names(new_output)
    newly_failing = sorted(new_failed - prior_failed)
    newly_passing = sorted(new_passed & prior_failed)
    if not newly_failing and not newly_passing:
        return None
    parts = []
    if newly_failing:
        parts.append(f"{len(newly_failing)} newly failing: {', '.join(newly_failing)}")
    if newly_passing:
        parts.append(f"{len(newly_passing)} newly passing: {', '.join(newly_passing)}")
    return "; ".join(parts)


# ---- shared discharge/suffix-match helpers ---------------------------------------------------
_BIND_BEFORE = 70
_KNOWN_PATH_EXT_RX = re.compile(r"(?:" + _PATH_EXT + r")\Z", re.IGNORECASE)
_LOCAL_GIT_TIMEOUT = 0.75
_PUSH_BRANCH_RX = re.compile(
    # Filler tokens between "to"/"branch" and the ref name ("pushed to branch X",
    # "pushed to the remote branch X") are skipped, not captured: capturing the literal
    # word after the first "to" verified refs like `refs/heads/branch` that cannot exist,
    # so the commonest truthful push phrasing was denied on a false fact.
    r"""\bpushed\b(?:(?![.!?\n]).){0,80}?\b(?:to|branch)\s+"""
    r"""(?:(?:the|a|my|new|remote|local|branch|origin)\s+)*[`'"]?"""
    r"""(?:origin/)?([A-Za-z0-9][A-Za-z0-9._/-]*)""",
    re.IGNORECASE,
)

def _path_components(p: str):
    """Normalized path split into components, dropping empties and a leading '~' (a home
    reference that never appears in a touched key)."""
    return [c for c in normalize_path(p).split("/") if c and c != "~"]
def _suffix_match(a_comps, b_comps) -> bool:
    """True iff the shorter component list is a TAIL (path-suffix) of the longer — so a bare/
    relative commitment ('settings.json', '~/.claude/CLAUDE.md') discharges against an absolute
    write ('/repo/.claude/CLAUDE.md'). The match is at a path-SEPARATOR boundary, which preserves
    the fakeexcuse firewall: 'auth.py' is NOT a suffix of 'auth_helper.py' (components
    ['auth_helper.py'] != ['auth.py']), only of '.../auth.py'. A dotless final component may
    also match that exact basename with one recognized extension (for informal references such
    as 'CHANGELOG' to the real file 'CHANGELOG.md')."""
    if not a_comps or not b_comps:
        return False
    short, long = (a_comps, b_comps) if len(a_comps) <= len(b_comps) else (b_comps, a_comps)
    if long[-len(short):] == short:
        return True

    # Component prefixes must still be an exact suffix; only the final component gets the
    # deliberate dotless-file leniency. On equal-length one-component inputs, prefer the
    # dotless side as the informal reference.
    if len(a_comps) == len(b_comps) and "." not in b_comps[-1] and "." in a_comps[-1]:
        short, long = b_comps, a_comps
    if long[-len(short):-1] != short[:-1]:
        return False
    short_final, long_final = short[-1], long[-1]
    if "." in short_final or not long_final.startswith(short_final + "."):
        return False
    return bool(_KNOWN_PATH_EXT_RX.fullmatch(long_final[len(short_final) + 1:]))
def _safe_size(fs_size, location):
    """fs_size(location) -> int|None, swallowing errors. None means 'size unknown' (fail-open)."""
    if fs_size is None:
        return None
    try:
        return fs_size(location)
    except Exception:
        return None
DISCHARGE_EATS = frozenset({"touched", "fs_exists", "empty", "fs_size"})
"""GateContext fields forwarded by `_discharge_kwargs`; pinned by the SIGNATURE law test."""

def _discharge_kwargs(c) -> dict:
    """The four GateContext fields a `_discharged()`-style gate needs, forwarded as kwargs from a
    GateContext `c`. Single-sources the "these are the discharge-relevant fields" convention so a
    gate's `run=lambda c: ...` wiring doesn't hand-repeat `touched_keys=c.touched,
    fs_exists=c.fs_exists, empty_keys=c.empty, fs_size=c.fs_size` at every call site."""
    return dict(touched_keys=c.touched, fs_exists=c.fs_exists, empty_keys=c.empty, fs_size=c.fs_size)


def _discharged(location: str, touched_keys, fs_exists, *, empty_keys=None, fs_size=None) -> bool:
    """A located commitment is discharged if a recorded touch or the live filesystem backs it —
    now CONTENT-deep (§7.1): a touch whose Write was zero-byte, or a file the disk shows at zero
    bytes, does NOT discharge a production claim, EXCEPT conventional empties (`__init__.py` etc.)
    whose emptiness IS the deliverable. Unknown size fails open (discharges) so a dropped or
    relocated file never false-blocks. Component-suffix match is at a separator boundary — never
    raw substring (the fakeexcuse firewall: auth.py never matches auth_helper.py).

    `fs_exists` is an optional `(location) -> bool` (the live os.path check). `empty_keys` are
    ledger keys whose latest Write produced zero substance ('touched' value='0'). `fs_size` is an
    optional live `(location) -> int|None`."""
    loc = normalize_path(location)
    keys = {normalize_path(k) for k in (touched_keys or ())}
    empties = {normalize_path(k) for k in (empty_keys or ())}
    conventional = os.path.basename(loc) in _EMPTY_OK
    lc = _path_components(location)

    def _matches(k):
        return k == loc or (bool(lc) and _suffix_match(lc, _path_components(k)))

    matched = {k for k in keys if _matches(k)}
    if matched:
        if conventional or any(k not in empties for k in matched):
            return True                              # substance recorded (or honest empty)
        # every matched touch is a zero-byte Write of a non-conventional file -> consult disk
        if fs_exists is not None and fs_exists(location):
            return _safe_size(fs_size, location) != 0    # exists non-empty -> discharged
        return False                                 # only an empty Write backs the claim
    if fs_exists is not None and fs_exists(location):  # fail-open re-derivation of a dropped touch
        if not conventional and _safe_size(fs_size, location) == 0:
            return False                             # exists but empty -> no production discharge
        return True
    return False


def _default_veto(claim, _c, *, touched_keys, fs_exists, empty_keys=None, fs_size=None) -> bool:
    """Default veto: treat the claim as a location and ask the shared discharge test.

    An ADAPTER, not sugar. `_discharged` is `(location, touched_keys, fs_exists, *, ...)`, but a
    veto is called `(claim, ctx, **facts)` -- so naming `_discharged` itself as the default handed
    the `GateContext` to the `touched_keys` slot positionally AND again as a keyword:
    `TypeError: _discharged() got multiple values for argument 'touched_keys'`, raised at Stop, i.e.
    a decision error and a spurious fail-CLOSED block, for any caller that did not pass its own
    `veto=`. Latent only because the sole caller today does.
    """
    location = claim.get("location", "") if isinstance(claim, dict) else claim
    return _discharged(location, touched_keys, fs_exists,
                       empty_keys=empty_keys, fs_size=fs_size)


class _CarriageFault(str):
    """Truthy sentinel for "Git did not answer", distinct from "the path is absent"."""
    __slots__ = ()


CARRIAGE_FAULT = _CarriageFault("<git carriage fault>")


def resolve_in_worktree(loc, cwd):
    """Resolve a repo-relative claim from `cwd`'s Git worktree root.

    Return an existing path, None, or `CARRIAGE_FAULT`. The candidate is confined to the worktree root, and every
    successful return ends in a live existence check. Tracking is not required: the cwd-relative
    filesystem discharge already accepts a newly-created, untracked deliverable.
    """
    if not loc or not cwd:
        return None
    try:
        if os.path.isabs(loc):
            return os.path.normpath(loc) if os.path.exists(loc) else None
        root_result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_LOCAL_GIT_TIMEOUT,
        )
        if root_result.returncode != 0:
            return None
        root_out = root_result.stdout.strip()
        if not root_out:
            # Guard BEFORE realpath: os.path.realpath("") returns the hook process's cwd,
            # which made this branch dead and re-rooted the confinement check at the wrong tree
            # whenever rev-parse exited 0 with empty stdout.
            return None
        root = os.path.realpath(root_out)
        candidate = os.path.realpath(os.path.join(root, loc))
        if os.path.commonpath((root, candidate)) != root:
            return None
        return candidate if os.path.exists(candidate) else None
    except (OSError, subprocess.SubprocessError):
        # See `pushed_ref_matches_world`: `git` unreachable is a CARRIAGE fault, and returning None
        # spelled it "the deliverable is absent" -- the exact value that makes the caller DENY. The
        # worktree was never consulted, so absence was never established. Callers must treat this
        # sentinel as fail-open; it is truthy so a caller that ignores it fails safe rather than
        # denying, and identity-comparable so one that handles it can.
        return CARRIAGE_FAULT
    except Exception:
        return None


def extract_pushed_branch(text):
    """The branch name from a "pushed ... to/branch X" claim in `text`, trailing
    quote/punctuation stripped -- or None if no such claim is present.

    One extraction step; each caller keeps its own downstream use (this module validates
    against local/remote refs, claimedShippedAbsent compares tips)."""
    match = _PUSH_BRANCH_RX.search(text or "")
    return match.group(1).rstrip("`'\",:;.") if match else None


def pushed_ref_matches_world(text, cwd):
    """True iff local and origin remote-tracking refs back a pushed-branch claim."""
    if not text or not cwd:
        return False
    try:
        branch = extract_pushed_branch(text)
        if branch is None:
            branch_result = subprocess.run(
                ["git", "-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_LOCAL_GIT_TIMEOUT,
            )
            if branch_result.returncode != 0:
                return False
            branch = branch_result.stdout.strip()
        if (
            not branch
            or branch.startswith(("-", ".", "/"))
            or branch.endswith((".", "/", ".lock"))
            or ".." in branch
            or "@{" in branch
            or "//" in branch
        ):
            return False
        refs = (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}")
        result = subprocess.run(
            ["git", "-C", cwd, "show-ref", "--verify", "--hash", *refs],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_LOCAL_GIT_TIMEOUT,
        )
        object_ids = result.stdout.splitlines()
        return result.returncode == 0 and len(object_ids) == 2 and object_ids[0] == object_ids[1]
    except (OSError, subprocess.SubprocessError):
        # CARRIAGE, not evidence. `git` missing from PATH, the _LOCAL_GIT_TIMEOUT budget blown, any
        # OS error -- none of them observed anything about the refs, yet `return False` handed the
        # caller the same value a genuine mismatch produces, and the caller DENIES on False. A real
        # push then read as unpushed and the deny asserted a fact nobody established. This repo's
        # rule is open on carriage, closed on decision, so an unanswered question does not
        # contradict the claim.
        return True
    except Exception:
        return False


def _event_type_of(row) -> str:
    """The hook event name of a history row, across both shapes: the production events-table tuple
    (id, ts, event_type, cwd, payload) carries it at index 2; the corpus-replay dict carries it
    under 'event_type'. Unknown shape -> '' (counted as neither a tool call nor a boundary)."""
    if isinstance(row, (tuple, list)) and len(row) > 2:
        return row[2] or ""
    if hasattr(row, "get"):
        return row.get("event_type", "") or ""
    return ""


def turn_tool_calls(history) -> int:
    """Number of tool calls the agent made in the CURRENT turn — the PreToolUse events after the most
    recent Stop boundary in the history slice. Production wires PreToolUse with matcher '*' (one event
    per tool call, every tool type — so Workflow/Agent/Task are NOT invisible here); a Stop event marks
    a turn boundary. PostToolUse is the same call's completion, not a new call, so only PreToolUse is
    counted. This is the fabricated-action gate's discharge: >0 means real tool work backs the turn's
    action claim, immune to command paraphrase and to invisible tools (token cost -> temperance)."""
    count = 0
    for row in history or ():
        et = _event_type_of(row)
        if et == "Stop":
            count = 0                      # new turn -> reset; only events after the final Stop count
        elif et == "PreToolUse":
            count += 1
    return count
