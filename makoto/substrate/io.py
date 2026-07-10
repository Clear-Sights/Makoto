"""lib/io.py (L1) — tool/event I/O parsing: payload decode, Bash output, test-run detection.

Pure-Python ports of Phase 4's install-helpers/predicates.sh helpers. Knight-Leveson:
stdlib only (json, regex). No HTTP, no LLM, no DuckDB. L1 primitive — imports only L0
lexicons. Consumed by the history-walking predicate (content.fabricated_commit_sha), the ledger, and the Stop
green-claim gate. Behaviour-first names (Task 6 dissolution of predicates/helpers.py into
lib.io / substrate.claims / substrate.factories / citations); no compat shim (CLAUDE.md #4).
"""
from __future__ import annotations
import json

from makoto.core.lexicons import _TEST_RUNNER_RX, _FAILURE_SUMMARY_RX, _FAILURE_MARKER_RX, _ANSI_SGR_RX


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
        return raw if isinstance(raw, dict) else json.loads(raw)
    except Exception:
        return None


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
    return bool(command) and bool(_TEST_RUNNER_RX.search(command))


def iter_tool_events(history):
    """Yield (tool_name, command, response_text) per prior tool event in `history`. Rows are the
    (id, ts, event_type, cwd, raw_payload_json) tuples _dispatch._select_recent returns, OR dicts
    with a 'payload' key (the shape measure_corpus_fp builds). The faithful events-table source
    (full command + full tool_response, like predicate content.unsourced_webfetch) — NOT the lossy ledger. Fail-open: an
    unparseable row is skipped, so a malformed event can never crash a Stop gate.

    Relocated VERBATIM from stopchecks/_common.py (2026-06-09 consolidation T2.5): the one
    history-row decoder lives at L1 beside raw_payload_str; consumers (named_test,
    precheck_1_22's _real_commit_in_history) import from here. NOTE: tolerates dict payloads
    (raw if isinstance(raw, dict)), deliberately MORE permissive than the str-only
    raw_payload_str path — corpus byte-comparison (T2.6) arbitrates that the union changes nothing.

    Decode step delegates to decode_history_row (2026-07-09 dedup); the isinstance(row, ...) sniff
    is intentionally NOT re-inlined here so this stays a single source, but the caller-side
    behavior is unchanged bit-for-bit — a non-dict `ev` (e.g. a JSON array payload) still falls
    through to `ev.get(...)` exactly as before, rather than gaining a new silent-skip branch."""
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
