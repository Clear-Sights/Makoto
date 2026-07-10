"""Makoto :: wire.py — the wire protocol seam (posture enum -> host JSON).

Intent: Be the ONE zero-inspection lookup table from ``posture.py``'s folded posture enum
(``BLOCK | ASK | ADVISE | ALLOW``) to a Claude Code hook response, re-deriving NO policy and
failing OPEN on every renderer path (a lookup miss returns ``{}`` — never an exception).

SPEC-5 (Makoto absorbs Assay): this module is a copy-BY-SHAPE of Assay's
``adapters/hook_bridge.py`` (its ``_PRE_WIRE``/``_STOP_WIRE``/``_POST_WIRE`` tables and renderers,
``hook_bridge.py:148-222``) — the logic and doc intent are ported, but this file does NOT import
from ``assay`` (repo boundary law: shapes are copied, never imported, across the faculties; Assay
retires later, so Makoto's wire module must stand alone).

ZERO INSPECTION. ``dispatch_posture`` maps a live edge name to the matching table and looks the
folded posture up in it — one table per hook edge, keyed by the enum, no branching on message /
locus / arm. The posture carries no free-text reason (``posture.apply`` folds context away), so the
human-facing reason is a CONSTANT per posture, declared here beside its wire words — not a value
re-derived from check state. A ``posture.Decision``'s ``.detail`` coordinate, when present,
overrides the constant wording (see ``_detail``).

RETURN SHAPE. ``dispatch_posture(edge, posture, hook_name) -> dict`` returns the CC hook response
body only (no exit-code tuple — Task 1's public seam is a pure body renderer; the process's exit
code is the caller's concern, wired at Task 8's dispatch integration). This is the seam Task 8's
``_dispatch.py`` cutover calls.

WIRE TABLES, one per edge:
  * Pre  (``_PRE_WIRE``):  BLOCK -> deny, ASK -> ask, ADVISE -> allow + ``additionalContext``,
    ALLOW -> absent (``{}`` — proceed untouched).
  * Stop / SubagentStop (``_STOP_WIRE``): BLOCK -> block the stop (``decision: "block"``, echoing
    whichever of the two edges actually fired via ``hookEventName``); everything else -> ``{}``.
  * Post (``_POST_WIRE``): ADVISE -> allow + ``additionalContext``; everything else -> ``{}`` — the
    audit edge is otherwise silent and NEVER emits a deny/block key, regardless of posture.

AGNOSTIC: no I/O, no env read, stdlib only. FAIL-OPEN: an edge name / posture the tables don't
recognize renders ``{}`` (no objection) rather than raising.
"""

from __future__ import annotations

from typing import Callable, Dict

from makoto.verdict import posture as _posture
# --- the Claude Code hook-event names (the edge the native feed tags each event with) -----------
_PRE_TOOL_USE = "PreToolUse"
_POST_TOOL_USE = "PostToolUse"
_STOP = "Stop"
_SUBAGENT_STOP = "SubagentStop"

# --- the edge names ``dispatch_posture`` accepts (its ``edge`` argument) -------------------------
_EDGE_PRE = "Pre"
_EDGE_POST = "Post"
_EDGE_STOP = "Stop"
_EDGE_SUBAGENT_STOP = "SubagentStop"

# --- the constant human-facing reasons (one per posture; a bare posture carries no message) ------
_DENY_REASON = (
    "makoto: blocked — a declared commitment is unfinished, or the operation targets a "
    "forbidden location / is structurally malformed"
)
_ASK_REASON = "makoto: human adjudication required for this step"
_ADVISE_REASON = "makoto: this name was already worked at another location"
_POST_ADVISE_REASON = (
    "makoto: a recorded contradiction was detected after this call (a name now "
    "resolves to more than one location, or a repeat/failure loop) — reconcile "
    "the prior location before continuing"
)
_STOP_REASON = "makoto: the declared plan is unfinished"


def _detail(posture_value, fallback: str) -> str:
    """Intent: Read the decision's coordinate detail (``posture.Decision.detail`` — the exact prior
    locations / unmet establishers a check saw), falling back to the constant wording when the
    posture carries none (a plain-string posture, or nothing to say)."""
    text = getattr(posture_value, "detail", "")
    return f"makoto: {text}" if text else fallback


def _pre_deny(posture_value) -> dict:
    """Intent: Render the PreToolUse ``deny`` response — a blocking preventive finding, carrying
    the exact coordinates (the unmet commitments / forbidden target) when the check named them."""
    return {
        "hookSpecificOutput": {
            "hookEventName": _PRE_TOOL_USE,
            "permissionDecision": "deny",
            "permissionDecisionReason": _detail(posture_value, _DENY_REASON),
        }
    }


def _pre_ask(posture_value) -> dict:
    """Intent: Render the PreToolUse ``ask`` response — an abstention escalated to the human."""
    return {
        "hookSpecificOutput": {
            "hookEventName": _PRE_TOOL_USE,
            "permissionDecision": "ask",
            "permissionDecisionReason": _detail(posture_value, _ASK_REASON),
        }
    }


def _pre_advise(posture_value) -> dict:
    """Intent: Render the PreToolUse advisory — allow, but inject the prior-location context IN THE
    BACKGROUND with its EXACT coordinates: the call proceeds, the prior location is named so it
    cannot be silently forgotten, nothing is denied."""
    return {
        "hookSpecificOutput": {
            "hookEventName": _PRE_TOOL_USE,
            "additionalContext": _detail(posture_value, _ADVISE_REASON),
        }
    }


# --- the zero-inspection tables: posture enum -> the response body renderer (one per edge) ------
# PreToolUse: BLOCK -> deny, ASK -> ask, ADVISE -> allow+context, ALLOW -> absent (proceed
# untouched — ``dispatch_posture``'s ``{}`` default). Lookup is by the enum VALUE; the renderer
# receives the posture so a ``Decision``'s coordinates reach the wire without the table inspecting
# anything.
_PRE_WIRE: Dict[str, Callable] = {
    _posture.BLOCK: _pre_deny,
    _posture.ASK: _pre_ask,
    _posture.ADVISE: _pre_advise,
}


def _stop_block(posture_value, hook_name: str) -> dict:
    """Intent: Render the Stop/SubagentStop ``block`` response — a blocking preventive finding for
    an unfinished plan / unreconciled contradiction, carrying the exact coordinates when the check
    named them AND which edge actually fired (``Stop`` vs ``SubagentStop``), so a sub-agent's own
    completion claim is distinguishable from a main-thread Stop in the wire body itself, not just
    inferred from which process received it."""
    return {
        "decision": "block",
        "reason": _detail(posture_value, _STOP_REASON),
        "hookEventName": hook_name,
    }


# Stop / SubagentStop: BLOCK -> block the stop (unfinished plan / unreconciled contradiction, with
# coordinates); everything else -> {} (allow). ASK / ADVISE / ALLOW never block the agent from
# stopping. The renderer takes the posture (coordinates) AND the actual hook name that fired, so
# one table serves both edges without re-deriving which one it was.
_STOP_WIRE: Dict[str, Callable] = {
    _posture.BLOCK: _stop_block,
}


def _post_advise(posture_value) -> dict:
    """Intent: Render the PostToolUse advisory — allow, but surface the detective finding (drift /
    stuck) as background ``additionalContext`` carrying its exact coordinates. The audit edge never
    denies; it informs."""
    return {
        "hookSpecificOutput": {
            "hookEventName": _POST_TOOL_USE,
            "additionalContext": _detail(posture_value, _POST_ADVISE_REASON),
        }
    }


# PostToolUse: ADVISE -> allow + context (a fired detective surfaced in the background); everything
# else -> {} (the audit edge is otherwise silent — it records, advances, and never objects).
_POST_WIRE: Dict[str, Callable] = {
    _posture.ADVISE: _post_advise,
}

# --- the edge -> table map (``dispatch_posture``'s own zero-inspection lookup) -------------------
_EDGE_TABLES: Dict[str, Dict[str, Callable]] = {
    _EDGE_PRE: _PRE_WIRE,
    _EDGE_POST: _POST_WIRE,
    _EDGE_STOP: _STOP_WIRE,
    _EDGE_SUBAGENT_STOP: _STOP_WIRE,
}

# Edges whose renderer needs the firing hook name (the Stop-shaped ones only; Pre/Post renderers
# hardcode their own constant ``hookEventName``, matching the source shape verbatim).
_HOOK_NAME_EDGES = (_EDGE_STOP, _EDGE_SUBAGENT_STOP)


def dispatch_posture(edge: str, posture_value: str, hook_name: str) -> dict:
    """Intent: The public seam — map ONE folded posture at ONE hook edge to a Claude Code hook
    response body, re-deriving no policy. This is what Task 8's ``_dispatch.py`` cutover calls.

    ``edge`` is one of ``"Pre"`` / ``"Post"`` / ``"Stop"`` / ``"SubagentStop"``. ``posture_value``
    is a folded posture (``posture.BLOCK`` / ``ASK`` / ``ADVISE`` / ``ALLOW``, or a ``Decision``
    carrying coordinates). ``hook_name`` is the actual Claude Code hook-event name that fired
    (``"Stop"`` or ``"SubagentStop"``) — only the Stop-shaped edges echo it back in the body; the
    Pre/Post renderers use their own constant ``hookEventName``, matching the source shape.

    FAIL-OPEN: an unrecognized ``edge`` or a posture with no entry in that edge's table both
    render ``{}`` (no objection) — never an exception. The Post edge's table only ever holds an
    ADVISE entry, so BLOCK/ASK/ALLOW at Post structurally can never render anything but ``{}``.
    """
    table = _EDGE_TABLES.get(edge)
    if table is None:
        return {}
    render = table.get(posture_value)
    if render is None:
        return {}
    if edge in _HOOK_NAME_EDGES:
        return render(posture_value, hook_name)
    return render(posture_value)
