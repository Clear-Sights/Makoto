"""makoto.substrate._shared — the Stop-edge gate catalog's own shared substrate (SPEC-5 Task 4,
owner-revised layout). Combines the former `stopchecks/_types.py` (the `GateContext` schema --
`StopCheck` itself was retired 2026-07-10 alongside `load_stopchecks()`, see `_loader.py`) and
`stopchecks/_common.py` (the discharge/suffix-match/turn-tool-call helpers every ledger-gate
shares) into ONE flat, underscore-prefixed file — package plumbing, never a detector module
itself, so `checks._loader`'s scan skips it exactly like `_primitives.py`/`_declared.py`.

Kept as ONE file (not split) because combined the two source files are ~150 lines — not the
"gets unwieldy" threshold the migration ticket flags as the split trigger — and every gate that
needs `GateContext` also tends to need at least one of the discharge helpers, so a single import
line (`from makoto.substrate._shared import ...`) serves every migrated gate module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from makoto.checks import normalize_path
from makoto.substrate._planNode import Plan
from makoto.core.lexicons import _EMPTY_OK


# ---- schemas (formerly stopchecks/_types.py) --------------------------------------------------
@dataclass(frozen=True)
class GateContext:
    """The Stop-event substrate, assembled ONCE per event and shared by every gate."""
    text: str
    touched: frozenset
    empty: frozenset
    opens: Sequence
    testrun_output: str
    cwd: str
    fs_exists: Callable
    fs_size: Callable
    fs_read: Callable
    history: Sequence = ()     # the events-table rows _select_recent returns (faithful: full
    #                            command + full tool_response per prior tool event). Fabrication
    #                            gates walk this like predicate content.unsourced_webfetch; default () keeps it optional.
    permission_mode: Optional[str] = None   # raw hook payload's `permission_mode` field verbatim
    #   (CONFIRMED real, snake_case, top-level on every hook event — Claude Code hooks reference,
    #   fetched 2026-07-06: "default"|"plan"|"acceptEdits"|"auto"|"dontAsk"|"bypassPermissions").
    #   No gate reads this yet (additive/observability-only per this ticket's scope).
    agent_id: Optional[str] = None          # raw `agent_id` — present only when the hook fired
    #   inside a subagent call (CONFIRMED real, top-level, per the same hooks reference). The
    #   nearest real substrate to a "this is a subagent" flag; no literal isSubAgent/isSidechain
    #   field exists in the documented schema, so this is the grounded substitute, not a guess.
    agent_type: Optional[str] = None        # raw `agent_type` (e.g. "Explore") — companion to
    #   agent_id, present when the session uses --agent or the hook fires inside a subagent.
    plan: Optional[Plan] = None             # the declared contract Plan (SPEC-5) for this
    #   session, loaded once by run_stop_checks via makoto.session.plan.load_plan; None when no plan is
    #   declared. Read by contractOrder's Stop GATE and staleEstablisher's advisory check.
    session_id: Optional[str] = None        # raw hook payload's `session_id` (Task 2 slice 5).
    transcript_path: Optional[str] = None   # raw `transcript_path` (CONFIRMED real, top-level on
    #   every hook event -- Claude Code hooks reference, fetched 2026-07-07: "Path to conversation
    #   JSONL file"). Read by canonFingerprints.py's release.operator discharge (makoto.record.ackblock).
    state_root: Optional[object] = None     # the resolved state dir (Path), threaded through so
    #   the release.operator discharge can read/append the chain at the SAME root the dispatcher itself
    #   uses (never guessed via env-var fallback) -- same explicit-root discipline as audit.py.

    @property
    def roots(self):
        return [self.cwd]

    @property
    def is_subagent(self) -> bool:
        """derived convenience: True iff this Stop substrate was built from a subagent-context
        payload (agent_id present) rather than the main agent."""
        return bool(self.agent_id)


# ---- shared discharge/suffix-match helpers (formerly stopchecks/_common.py) --------------------
_BIND_BEFORE = 70
def _path_components(p: str):
    """Normalized path split into components, dropping empties and a leading '~' (a home
    reference that never appears in a touched key)."""
    return [c for c in normalize_path(p).replace("\\", "/").split("/") if c and c != "~"]
def _suffix_match(a_comps, b_comps) -> bool:
    """True iff the shorter component list is a TAIL (path-suffix) of the longer — so a bare/
    relative commitment ('settings.json', '~/.claude/CLAUDE.md') discharges against an absolute
    write ('/repo/.claude/CLAUDE.md'). The match is at a path-SEPARATOR boundary, which preserves
    the fakeexcuse firewall: 'auth.py' is NOT a suffix of 'auth_helper.py' (components
    ['auth_helper.py'] != ['auth.py']), only of '.../auth.py'."""
    if not a_comps or not b_comps:
        return False
    short, long = (a_comps, b_comps) if len(a_comps) <= len(b_comps) else (b_comps, a_comps)
    return long[-len(short):] == short
def _safe_size(fs_size, location):
    """fs_size(location) -> int|None, swallowing errors. None means 'size unknown' (fail-open)."""
    if fs_size is None:
        return None
    try:
        return fs_size(location)
    except Exception:
        return None
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


# iter_tool_events RELOCATED to lib/io.py (consolidation T2.5): the history-row decoder lives at
# L1 beside raw_payload_str/decode_payload; consumers import `from makoto.substrate.io import iter_tool_events`.
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
