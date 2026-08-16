"""makoto.kit — the shared check-building kit (Stage 2 seam 4): the former
`substrate/factories.py` (L1 predicate factories + AST primitives), `substrate/io.py`
(tool/event I/O parsing: payload decode, Bash output, test-run detection),
`substrate/_primitives.py` (deterministic location/quantity/subject primitives),
`substrate/_failureClassifier.py` (transient-vs-deterministic failure classification),
`substrate/_testDelta.py` (per-test verdict delta), and `substrate/_shared.py`'s shared
gate helpers (everything except the `GateContext` schema, which stays behind pending its
own extraction into `context.py`) — merged verbatim, one flat module. Each section below
keeps its source file's own docstrings/comments; logic is byte-for-byte unchanged.

Stdlib only; no HTTP, no LLM (Knight-Leveson hot-path invariant). Imports only L0
(`makoto.vocab`, `makoto.core._shell`); `compute_delta`'s reuse of namedTestTeeth's
parsers stays a call-time import exactly as its `dispatch.py` consumer already was,
so the kit never carries an import-time edge into a named check module.
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
    _TEST_RUNNER_RX,  # compatibility export pinned by tests/test_lexicons.py
    _FAILURE_SUMMARY_RX,
    _FAILURE_MARKER_RX,
    _ANSI_SGR_RX,
    _EMPTY_OK,
    _MAKOTO_ALLOW_RX,
    _MAKOTO_ALLOW_REASON_RX,
    _PATH_EXT,
    Finding,
    JWT_CALLEE_RX,
)

# `pattern:` arguments below are typed `Check` (registry.Check) only in a docstring/
# comment sense, never a real import: this L1 module's own layering firewall
# (tests/lib/test_factories.py) bars it from importing the registry (an L2+ module) even for a
# type hint. `from __future__ import annotations` (top of file) means annotations are never
# evaluated at runtime, so the bare `Check` name in each signature below resolves to nothing at
# runtime and is safe -- it exists purely for readers, not as a real dependency edge.


# ---- deterministic check primitives (formerly substrate/_primitives.py) -----------------------
# Location is normalized-path EQUALITY (not substring — equality is the fakeexcuse
# firewall). Quantity is a number compare. Subject-binding gates retraction reasons.

def normalize_path(p: str) -> str:
    """Case-folded, normalized, trailing-separator-stripped path for equality.

    Separators are forced to forward-slash so a claim/commitment/touched identity is
    platform-stable: os.path.normpath emits '\\' on Windows, which would make the same
    logical path mismatch its POSIX-authored form (Windows-portability fix)."""
    if not p:
        return ""
    return os.path.normcase(os.path.normpath(p.strip())).rstrip("/\\").replace("\\", "/")


def location_match(location: str, touched_keys) -> bool:
    """True iff the named location EQUALS (normalized) one of the touched keys.

    Equality, never substring: 'auth.py' must NOT match 'auth_helper.py'.
    """
    loc = normalize_path(location)
    if not loc:
        return False
    return any(normalize_path(k) == loc for k in touched_keys)


def quantity_match(value, *, n=None, lo=None, hi=None) -> bool:
    """True iff `value` equals `n`, or falls within [lo, hi]. None value -> False."""
    if value is None:
        return False
    if n is not None:
        return value == n
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return lo is not None or hi is not None


def subject_binds(commitment_location: str, result_key: str) -> bool:
    """A cited result is 'about' a commitment iff its key EQUALS (normalized) the
    commitment location. Equality (not containment) kills the fakeexcuse vector:
    an empty `fakeexcuse.txt` cannot stand in for a commitment at `auth.py`.
    """
    return normalize_path(commitment_location) == normalize_path(result_key)


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
# A quantity is a number (optionally a `Nx` / `N×` speedup), or a range
# (`N-M`, `N to M`, `N and M`). Decimals allowed (e.g. 2.4x) — the `x`/`×` suffix is
# why a trailing `\b` after the digits won't do: in "2x" the digit is glued to a letter.
_QTY_RX = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:[-–]|to|and)\s*(\d+(?:\.\d+)?)\b"
    r"|\b(\d+(?:\.\d+)?)(?:[x×])?\b"
)


def detect_location(text: str):
    """Return the first located file path in `text`, or None if the claim is unlocated."""
    m = _LOC_RX.search(text or "")
    return m.group(0) if m else None


def detect_locations(text: str):
    """Yield (location, start, end) for every located file path in `text`, in order.

    Used by the completion gate to bind a production claim to the right path when a
    message names several (the producing verb may govern the second, not the first)."""
    for m in _LOC_RX.finditer(text or ""):
        yield (m.group(0), m.start(), m.end())


def detect_quantity(text: str):
    """Return (lo, hi) for a quantity claim (exact N -> (N, N)), or None.

    Floats, so a speedup like 2.4x compares correctly; integer values are equal to
    their int form ((3, 3) == (3.0, 3.0)) so existing callers are unaffected.
    """
    m = _QTY_RX.search(text or "")
    if not m:
        return None
    if m.group(1):
        return (float(m.group(1)), float(m.group(2)))
    return (float(m.group(3)), float(m.group(3)))


def bash_nonempty_violation(tool_response: dict) -> bool:
    """Constant invariant: a Bash command's output should be non-empty — BUT honor
    the harness's own `noOutputExpected` signal. Fires only when output is empty
    AND exit code is 0 AND noOutputExpected is False (so `mkdir`/`touch` never fire).
    """
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("noOutputExpected") is True:
        return False
    out = (tool_response.get("stdout") or "") + (tool_response.get("stderr") or "")
    exit_code = tool_response.get("exitCode", tool_response.get("exit", 0)) or 0
    return out.strip() == "" and exit_code == 0


# ---- tool/event I/O parsing (formerly substrate/io.py) ----------------------------------------
# Pure-Python ports of Phase 4's install-helpers/predicates.sh helpers. Knight-Leveson:
# stdlib only (json, regex). No HTTP, no LLM, no DuckDB. Consumed by the history-walking
# predicate (content.fabricated_commit_sha), the ledger, and the Stop green-claim gate.

def raw_payload_str(entry) -> str:
    """history row -> the raw payload JSON string ('' for anything undecodable).

    events-table rows are 5-tuples (id, ts, event_type, cwd, payload_json); some callers pass
    dict-likes with a 'payload' key. Exposed for callers that need the raw string itself
    (content.fabricated_commit_sha's grounded-SHA substring scan) — formerly a byte-identical local copy in precheck_1_22.
    """
    if isinstance(entry, (tuple, list)) and len(entry) >= 5:
        raw = entry[4]
    elif hasattr(entry, "get"):
        raw = entry.get("payload", "")
    else:
        raw = ""
    return raw if isinstance(raw, str) else ""


def decode_history_row(row):
    """Decode one history row's raw JSON payload into an event dict, or None if the row is
    malformed/absent/unparseable. Rows are either the (id, ts, event_type, cwd, raw_payload_json)
    5-tuples the events table returns, or dict-likes carrying a 'payload' key (corpus replay).
    Fail-open: an undecodable row yields None rather than raising, so one malformed row can never
    crash a caller's scan.

    The ONE canonical row-decode step (found triplicated by jscpd, 2026-07-09: iter_tool_events
    below, substrate._canonAtoms._decode_row, and checks.writeThrashRevert._prior_whole_file_writes
    each re-derived this same tuple/dict-payload sniff + json.loads by hand). Callers keep their own
    downstream shape/filter (a Call dict, a (name, command, response) tuple, a ByteIdentity list) --
    only the shared decode-to-dict step lives here."""
    if isinstance(row, (tuple, list)) and len(row) > 4:
        raw = row[4]
    elif hasattr(row, "get"):
        raw = row.get("payload")
    else:
        raw = None
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

    Two checks (`canonTimeoutRecur._decode_row`, `identicalRetryInterdiction`) used to re-derive
    this fallback independently, each a byte-similar copy of the row-union handling above. One
    drifted: it read only the payload's own field, so a row whose event type lived solely on the
    wrapper decoded to a payload with no `hook_event_name` -- and `event.identical_retry`
    requires an exact `== "PostToolUse"` match, so it went silently blind to rows
    `canon.timeout`/`canon.recur` acted on, from the same table, for the same concept. One
    primitive now serves both -- see `decode_history_row`'s own docstring on why a shared decode
    step exists at all."""
    wrapper_etype = None
    if isinstance(row, (tuple, list)) and len(row) > 2:
        wrapper_etype = row[2]
    elif hasattr(row, "get"):
        wrapper_etype = row.get("event_type")
    ev = decode_history_row(row)
    if ev is None:
        return None
    if not ev.get("hook_event_name") and wrapper_etype:
        ev = {**ev, "hook_event_name": wrapper_etype}
    return ev


def bash_output_text(tool_response) -> str:
    """extract captured stdout+stderr from a Bash tool_response.

    PRODUCTION SHAPE (verified vs the real makoto events DB): Bash PostToolUse
    tool_response is a DICT with keys stdout/stderr/interrupted/isImage/
    noOutputExpected. We pull stdout and stderr. str / list are tolerated for the
    synthetic-test payload shape. Shared by the ledger (records Bash result rows);
    formerly defined in pattern_2_6, kept here after that pattern was cut."""
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
    (full command + full tool_response, like predicate content.unsourced_webfetch) — NOT the lossy ledger. Fail-open: an
    unparseable row is skipped, so a malformed event can never crash a Stop gate.

    Relocated VERBATIM from stopchecks/_common.py (2026-06-09 consolidation T2.5): the one
    history-row decoder lives at L1 beside raw_payload_str; consumers (named_test,
    precheck_1_22's _real_commit_in_history) import from here. NOTE: tolerates dict payloads
    (raw if isinstance(raw, dict)), deliberately MORE permissive than the str-only
    raw_payload_str path — corpus byte-comparison (T2.6) arbitrates that the union changes nothing.

    Decode step delegates to decode_history_row (2026-07-09 dedup); parsed JSON with the wrong
    envelope shape is skipped there just like invalid JSON, so it cannot crash this iterator."""
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


# ---- predicate factories + AST primitives (formerly substrate/factories.py) -------------------
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
# reach for it. Instead it exposes a SINK the L3 orchestrator injects (dependency inversion): the
# factory stays L0-import-pure and a pure unit call (no sink installed) is unchanged — it returns
# None on an exempted match exactly as before. The dispatcher wires the audit-writing sink at import,
# so in production every suppressed match is recorded; the detector never grows an audit dependency.
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
    """Shared gate scaffold of both content-scan factories below (found duplicated by jscpd,
    2026-07-09): PreToolUse-only, `target_rx` gates `file_path`, `exempt_rx` gates content.
    Returns `(fp, content)` to continue, or None to stay silent (mirrors each predicate's own
    "no opinion" return)."""
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
    """Shared tail of both content-scan factories below (found duplicated by jscpd, 2026-07-09,
    lines 174-181/242-249 and 201-208/262-272 of the pre-extraction file): DETECT-THEN-EXEMPT --
    record a suppressed match rather than silently drop it (R5b), else build the real Finding."""
    if makoto_allowed(content):
        _record_exemption(current_event, conn, pattern_id=pattern.id, file=fp,
                          line=line_no, reason=makoto_allow_reason(content) or "",
                          snippet=snippet)
        return None  # AI documented this instance as legitimate (see CLAUDE.md) — recorded
    return Finding(
        # Pre-tier checks are invariantly posture=BLOCK (enforced by
        # tests/test_pre_tier_block_invariant.py, no longer by a `.fire_level` field on the
        # pattern object -- `Check` has no `fire_level`, only `posture`), and Finding.level's
        # vocabulary ("error"/"advisory") is a separate axis from posture's ("BLOCK"/"ADVISE"/
        # ...), so this is a literal, not a `pattern.posture` passthrough.
        pattern_id=pattern.id, file=fp, line=line_no, level="error",
        message=message, retry_hint=pattern.retry_hint, snippet=snippet,
    )


def scan_target_content(tool_input: dict) -> str:
    """The NEW text a PreToolUse file-mutation introduces, for content-scan patterns.

    Write exposes the full new file as ``content``; Edit exposes its replacement as
    ``new_string``; MultiEdit exposes a list of ``{old_string, new_string}`` edits. We
    return the text being INTRODUCED (never ``old_string``), so an AI cannot weaken a
    verifier via Edit/MultiEdit and evade the content-scan patterns — the EDIT-CONTENT GAP
    (an AI could insert `.startswith(` into a verifier via Edit and slip past content.verifier_predicate_weakened) closed
    2026-06-01. Scanning only the introduced text (not the whole post-edit file) keeps Edit
    FP-safe: a pattern fires solely on a shape the AI is actively adding.
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
    Shared by every "would this call INTRODUCE a flagged string" predicate (content.illusory_authorship_trailer,
    content.illusory_interruption_claim, ...) — factored out (2026-07-19) after
    test_no_alpha_duplicate_functions caught two checks carrying a byte-identical local copy."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""
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
    otherwise. Shared callee gate for content.jwt_signature_disabled (verify=False / options-dict disable) and content.jwt_none_alg
    (algorithms=["none"] whitelisting) — both patterns need this SAME 'is this really a
    jwt.decode(...) call' precondition before inspecting their own distinct keyword (found
    duplicated by jscpd, 2026-07-09: the two predicates' node_match functions repeated this exact
    4-statement gate by hand)."""
    if not isinstance(node, ast.Call):
        return None
    chain = callee_chain(node)
    if not JWT_CALLEE_RX.search(chain):
        return None
    if chain.split(".")[-1] != "decode":
        return None
    return chain


def ast_introduced_predicate(
    *,
    target_rx: re.Pattern,
    node_match: Callable[[ast.AST], Optional[str]],
    exempt_rx: Optional[re.Pattern] = None,
    exempt_label: str = "",
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
        tree, off = parse_introduced(content)
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

    Replaces the 24-line copy-paste scaffold formerly duplicated across patterns
    1.1/1.2/1.3/1.4/1.5/1.8 — including 1.4/1.8, which fold their ADR-backlink
    carve-out into the optional `exempt_rx` below. Each predicate now declares its
    regex constants and instantiates this factory — module LoC drops from ~24 to ~5.

    Args:
      target_rx:    matched against `tool_input.file_path`; gate (None if no match)
      body_rx:      matched against `tool_input.content`; fires Finding on first hit
      exempt_rx:    optional SECOND exemption (beyond the universal makoto_allowed) — when it
                    matches the content, the predicate stays silent. This is the documented-
                    suppression carve-out 1.4/1.8 need (an `ADR-NNN` backlink exempts the finding).
      exempt_label: human label for exempt_rx; when set, a firing message gets the
                    ` with no <label>` suffix (preserves 1.4/1.8's exact wording).

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
                    claims.append(match.group(1) if match.groups() else match.group(0))
        for claimed in claims:
            if grounded_in_history(claimed, history):
                continue
            rendered = message(claimed, subject, pattern) if callable(message) else message.format(
                claimed=claimed, id=pattern.id, description=pattern.description
            )
            return Finding(
                pattern_id=pattern.id, file="", line=0, level="error", message=rendered,
                retry_hint=pattern.retry_hint, snippet=str(claimed if not subject else subject)[:200],
            )
        return None
    return _predicate


def _introduced_regex_scan(current_event: dict, body_rx: re.Pattern):
    """Shared scan step behind `introduced_regex_predicate`: scan ANY tool's INTRODUCED text (via
    `introduced_text` — Write/Edit/MultiEdit content OR a Bash command, not just a file-path-gated
    Write/Edit body the way `regex_file_predicate`'s `target_rx` requires) for `body_rx`. Returns
    None (no finding) or a (match, text, tool_input, tool_name) tuple for the caller to finish
    building a Finding from — see `introduced_regex_predicate`'s own docstring for how its callers
    diverge (a `grounded_in_history` veto or not) after this scan step.
    """
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = current_event.get("tool_name", "") or ""
    tool_input = current_event.get("tool_input", {}) or {}
    text = introduced_text(tool_name, tool_input)
    if not text:
        return None
    if makoto_allowed(text):
        return None  # universal exemption: AI documented this as legitimate (see CLAUDE.md)
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
    """Build a Pre predicate over `_introduced_regex_scan` + `_introduced_regex_finding` — the
    shared scaffold behind illusoryAuthorshipTrailer.py (PATTERN_MATCH: no `grounded_in_history`)
    and illusoryInterruptionClaim.py (CLAIM_VS_HISTORY: `grounded_in_history` supplied — when it
    returns True on `history`, a real instance of the claim IS on the record, so the finding is
    suppressed rather than raised).

    One factory, not two, because the shape distinction between these callers is genuinely just
    "is there a veto after the match" — the same shape `_introduced_regex_scan`'s own docstring
    already named as the real divergence point. `tests/test_check_law_tests.py`'s `_factory_shape`
    derives PATTERN_MATCH vs. CLAIM_VS_HISTORY from whether the call site passes
    `grounded_in_history=` — a literal AST check on the call's keywords, not a runtime value, so
    the law still VERIFIES the declared shape from source rather than trusting a name or a
    manifest (the failure mode the DSL/Rego/CEL angle of this session's prior-art investigation
    found and rejected for exactly this reason).
    """
    def _predicate(*, current_event: dict, history: list,
                   pattern: Check, conn=None) -> Optional[Finding]:
        hit = _introduced_regex_scan(current_event, body_rx)
        if hit is None:
            return None
        m, text, tool_input, tool_name = hit
        if grounded_in_history is None:
            return _introduced_regex_finding(pattern, m, text, tool_input, tool_name)
        if grounded_in_history(history):
            return None  # a real instance IS on the record -- the claim is grounded, not illusory
        return _introduced_regex_finding(pattern, m, text, tool_input, tool_name, veto_suffix)
    return _predicate


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


# ---- transient-vs-deterministic failure classification (formerly substrate/_failureClassifier.py)
# The ship-bar the design review named for D1 (identical-retry interdiction, docs/DEFERRED.md).
# Two design consultations converged on this exact requirement: a BLOCK-tier check denying a
# retry must never deny a LEGITIMATE re-poll of a transient failure (a timeout, a 5xx, "still
# running"), so this classifier is conservative -- it fails toward UNCERTAIN (None), never toward
# "assume deterministic", whenever the signal is ambiguous. "If the runtime cannot discriminate,
# the honest outcome is to cut or defer the check, not demote it to advisory" (design ruling,
# verbatim) -- this classifier is what makes discrimination possible at all;
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
    re.compile(r"\bconnection refused\b", re.IGNORECASE),
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


# ---- test-delta redirect (formerly substrate/_testDelta.py) -----------------------------------
# Task 3, the domain correction (owner: "Makoto owns block + redirect -- that is its entire
# domain"). This move started life in Lever's catalogue as "test-delta redirect" but is
# REDIRECT-shaped (reactive to a test run that just completed, not a proactive positive-
# positioning move) -- so per the owner's boundary it belongs here, not Lever.
#
# Wired DIRECTLY into `dispatch.py`'s PostToolUse branch, not the patterns.toml/load_prechecks
# catalog (Pre-only) nor the Stop-gate catalog (Stop-only) -- neither covers a Post-edge advisory
# today. This is a one-off wire, honestly disclosed at its call site, not hidden behind a catalog
# entry that would misleadingly imply broader dispatch-loader coverage than exists.
#
# `compute_delta` reuses `namedTestTeeth.py`'s OWN `recorded_failed_names`/`recorded_passed_names`
# parsers (one implementation, never a second one) to diff the per-test verdict set between the
# PRIOR recorded testrun output and the NEW one just produced -- grounding every downstream fix on
# the delta itself, not a re-read of the full pytest wall of text. The import is call-time (as its
# `dispatch.py` consumer's already was) so this kit module never carries an import-time edge into
# a named check module.

def compute_delta(prior_output: str, new_output: str) -> Optional[str]:
    """None when there's nothing to say: no prior run to diff against, or no verdict flipped.
    "Newly failing" = named tests failing now that were NOT already failing in the prior run;
    "newly passing" = named tests passing now that WERE failing in the prior run (a genuine
    fix). A test that was already failing and is STILL failing is neither -- not new information,
    so it stays out of the delta (grounding on what CHANGED, not the whole persistent state)."""
    from makoto.checks.namedTestTeeth import recorded_failed_names, recorded_passed_names
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


# ---- shared discharge/suffix-match helpers (formerly substrate/_shared.py, ex-stopchecks/_common.py)
_BIND_BEFORE = 70
_KNOWN_PATH_EXT_RX = re.compile(r"(?:" + _PATH_EXT + r")\Z", re.IGNORECASE)
_LOCAL_GIT_TIMEOUT = 0.75
_PUSH_BRANCH_RX = re.compile(
    r"""\bpushed\b(?:(?![.!?\n]).){0,80}?\b(?:to|branch)\s+[`'"]?"""
    r"""(?:origin/)?([A-Za-z0-9][A-Za-z0-9._/-]*)""",
    re.IGNORECASE,
)

def _path_components(p: str):
    """Normalized path split into components, dropping empties and a leading '~' (a home
    reference that never appears in a touched key)."""
    return [c for c in normalize_path(p).replace("\\", "/").split("/") if c and c != "~"]
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
    fs_exists=c.fs_exists, empty_keys=c.empty, fs_size=c.fs_size` at every call site (found
    duplicated by jscpd, 2026-07-09, between gate.completion and gate.advance's own `run=` lambdas)."""
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


def claim_vs_ledger_predicate(
    *, extract_claims, veto=_discharged, message,
) -> Callable[..., Optional[Finding]]:
    """Build a Stop check comparing extracted claims with the discharge ledger."""
    def _run(c):
        claims = extract_claims(c.text, c.opens)
        for claim in claims:
            if veto(
                claim, c,
                touched_keys=c.touched, fs_exists=c.fs_exists,
                empty_keys=c.empty, fs_size=c.fs_size,
            ):
                continue
            result = message(claim, c) if callable(message) else message.format(claim=claim)
            if isinstance(result, Finding):
                return result
            return Finding(
                pattern_id="", file="", line=0, level="error", message=result,
            )
        return None
    _run.__module__ = extract_claims.__module__
    return _run


def resolve_in_worktree(loc, cwd):
    """Resolve a repo-relative claim from `cwd`'s Git worktree root.

    Return an existing path or None. The candidate is confined to the worktree root, and every
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
            capture_output=True, text=True, timeout=_LOCAL_GIT_TIMEOUT,
        )
        if root_result.returncode != 0:
            return None
        root = os.path.realpath(root_result.stdout.strip())
        if not root:
            return None
        candidate = os.path.realpath(os.path.join(root, loc))
        if os.path.commonpath((root, candidate)) != root:
            return None
        return candidate if os.path.exists(candidate) else None
    except Exception:
        return None


def extract_pushed_branch(text):
    """The branch name from a "pushed ... to/branch X" claim in `text`, trailing
    quote/punctuation stripped -- or None if no such claim is present.

    Was two byte-identical regex-plus-rstrip pairs (`pushed_ref_matches_world` here and
    `checks/claimedShippedAbsent.pushed_tip_matches_remote`), each with its own postprocessing
    call site. One extraction step; each caller keeps its own downstream use (this module
    validates against local/remote refs, claimedShippedAbsent compares tips) -- the same
    shared-decode/caller-owned-interpretation split `decode_history_event` uses."""
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
                capture_output=True, text=True, timeout=_LOCAL_GIT_TIMEOUT,
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
            capture_output=True, text=True, timeout=_LOCAL_GIT_TIMEOUT,
        )
        object_ids = result.stdout.splitlines()
        return result.returncode == 0 and len(object_ids) == 2 and object_ids[0] == object_ids[1]
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
