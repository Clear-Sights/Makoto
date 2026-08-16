"""makoto.verdict — the verdict seam (Stage 2 seam 5): the former `verdict/posture.py`
(posture vocabulary + the MAKOTO_MODE fold), `verdict/wire.py` (posture enum -> host JSON wire
tables), and `verdict/recheck.py` (the F4 CONTENT-law verdict certificate) — merged verbatim,
one flat module: vocabulary -> fold -> wire -> certificate. Each section below keeps its source
file's own docstrings/comments; logic is byte-for-byte unchanged.

Seam 6 finished the plan's shape: with `configchange_verdict.py` merged into `configchange.py`,
the former `verdict/` package collapsed to this top-level `makoto/verdict.py` module (same
import surface — `from makoto import verdict` / `from makoto.verdict import ...` are unchanged).

Section 1 (posture) original module docstring follows.

Makoto :: posture.py — the ONE enforcement-posture home (the ``MAKOTO_MODE`` reader).

Intent: Read the configured ``MAKOTO_MODE`` posture and merge it with a raw check outcome into the
final posture the host acts on — the single place that decides how hard a contradiction bites.

SPEC-5 (Makoto absorbs Assay): this module is a copy-BY-SHAPE of Assay's ``runtime/mode.py`` —
the logic and doc intent are ported verbatim, but this file does NOT import from ``assay`` (repo
boundary law: no faculty imports another; shapes are copied, never imported, across
``assay/``/``staging/makoto/``/``staging/ventura/``/``staging/crucible/``). Assay retires later, so
Makoto's posture module must stand alone.

TWO vocabularies, ONE seam:
  * the CONFIGURED posture (env input): ``LOOSE | STRICT | ASK | SILENT`` — what the operator asked
    for. ``DEFAULT_POSTURE`` (``STRICT``) is what an unset / unrecognized env resolves to, so the
    invariant "unset enforces by default" holds.
  * the OUTCOME (a check's decision seam): ``BLOCK | ASK | ADVISE | ALLOW`` — what a check
    concluded before the posture is applied. A check returns one of these; this module's ``apply``
    folds the configured posture over it; ``wire.py`` is then a zero-policy lookup table from the
    folded OUTCOME to the host's wire words.

CONFIG-DRIVEN MERGE (the file's role): ``apply(outcome, posture_value)`` is a pure function — no
I/O, no env read of its own (the caller passes the posture it read via ``posture()``) — that merges
the operator's configured intent with the check's raw decision. It NEVER escalates a check that
found nothing (an ``ALLOW`` stays ``ALLOW`` under every posture); it only softens or hardens what a
check already flagged. AGNOSTIC: it reads posture strings and outcome tokens only, never work
content.

Layer-0 leaf: stdlib-only (imports nothing from the rest of the package), so the whole spine can
read the posture vocabulary without a dependency edge.
"""

from __future__ import annotations


import os

# --- the OUTCOME vocabulary (a check's decision seam, folded by posture, read by wire.py) -------
# The raw decision a check produces, BEFORE the configured posture is applied.
BLOCK = "block"  # a genuine, actionable contradiction — deny the call / block the stop
ASK = "ask"  # an abstention the host should escalate to the human (UNKNOWN-shaped)
ADVISE = "advise"  # a non-blocking advisory — surface prior context, never deny
ALLOW = "allow"  # nothing to say — the call / stop proceeds untouched

_OUTCOMES = (BLOCK, ASK, ADVISE, ALLOW)


class Decision(str):
    """Intent: A posture-enum value that CARRIES its structural coordinates — the exact prior
    locations / unmet establishers / diverging names a check saw — so the host can surface WHAT
    to reconcile, not just that something fired.

    A ``str`` subclass whose VALUE is the outcome token (so every ``== BLOCK`` comparison and
    wire-table lookup behaves exactly like the bare enum) and whose ``detail`` attribute is the
    human-facing coordinate string (``""`` when there is nothing to say). The detail holds only
    STRUCTURAL locators (paths, node ids, passthrough names) — never work content — so the
    agnostic wall holds. ``hash``/``eq`` are the str's own; the detail never affects identity.
    """

    detail: str

    def __new__(cls, outcome: str, detail: str = "") -> "Decision":
        obj = super().__new__(cls, outcome)
        obj.detail = detail
        return obj


# --- the configured POSTURE vocabulary (the ``MAKOTO_MODE`` env input) ---------------------------
# What the operator asked for. Each posture is a rule for FOLDING the outcome above (see ``apply``).
LOOSE = "loose"  # advise-only: soften a BLOCK to ADVISE (surface, do not deny)
STRICT = "strict"  # block: honor the raw outcome as-is (a BLOCK blocks) — the default
ASK_POSTURE = "ask"  # escalate: turn any actionable outcome (BLOCK/ASK) into an ASK to the human
SILENT = "silent"  # record only: no enforcement and no advisory — every outcome becomes ALLOW

_POSTURES = (LOOSE, STRICT, ASK_POSTURE, SILENT)

# Unset / unrecognized env -> STRICT. Enforcement is ON BY DEFAULT.
DEFAULT_POSTURE = STRICT

_MAKOTO_MODE_ENV = "MAKOTO_MODE"


def posture(env=None) -> str:
    """Intent: Resolve the configured ``MAKOTO_MODE`` posture from the environment, defaulting to
    STRICT so an unset / unrecognized value enforces (the on-by-default invariant).

    ``env`` (a mapping; ``os.environ`` when omitted) is read for ``MAKOTO_MODE`` and lower-cased.
    A recognized value returns that posture; anything else — including an empty string or an unset
    key — returns ``DEFAULT_POSTURE`` (STRICT). This is the ONLY env read in the module; ``apply``
    takes the resolved posture as an argument so it can stay a pure fold.
    """
    source = os.environ if env is None else env
    raw = source.get(_MAKOTO_MODE_ENV, "")
    value = raw.strip().lower() if isinstance(raw, str) else ""
    return value if value in _POSTURES else DEFAULT_POSTURE


# D6 (docs/DEFERRED.md, DESIGN DECISION 2026-07-07): the two permission_mode values where Claude
# Code's OWN human-confirmation layer is off. When the harness already isn't asking a human to
# confirm a tool call, an operator-configured softening (LOOSE/SILENT) makes a flagged check
# uncheckable in name only -- neither ADVISE (surfaces to an agent that auto-approves) nor ASK
# (defers to a human who is not in the loop) actually holds in these two modes. Forced to STRICT
# regardless of MAKOTO_MODE -- never overridden SILENTLY, though: `is_oversight_clamped` lets the
# caller record the clamp + the configured posture it overrode, per this repo's own invariant
# ("Makoto never looks away silently" cuts both ways -- it never overrides silently either). The
# `makoto-allow` annotation remains the legitimate, on-the-record per-instance escape hatch.
_REDUCED_OVERSIGHT_MODES = frozenset({"bypassPermissions", "dontAsk"})


def is_oversight_clamped(permission_mode) -> bool:
    """True iff `permission_mode` is one of the two modes where Claude Code's own human-
    confirmation layer is off (`apply` forces STRICT in this case regardless of MAKOTO_MODE)."""
    return permission_mode in _REDUCED_OVERSIGHT_MODES


def apply(outcome, posture_value, *, permission_mode=None, layer="object") -> str:
    """Intent: Fold the configured posture over a raw check outcome into the final posture the host
    acts on — softening or hardening what a check flagged, never escalating a check that found none.

    Pure merge (no I/O, no env read): ``outcome`` is one of ``BLOCK | ASK | ADVISE | ALLOW`` (a
    check's raw decision) and ``posture_value`` is a resolved posture (from ``posture()``). The
    fold rules, one per configured posture:
      * SILENT -> ALLOW always (record only; suppress every enforcement and advisory).
      * LOOSE  -> a BLOCK softens to ADVISE (surface, never deny); ASK / ADVISE / ALLOW pass through.
      * ASK    -> a BLOCK or ASK escalates to ASK (defer to the human); ADVISE / ALLOW pass through.
      * STRICT -> the raw outcome is honored as-is (a BLOCK blocks).
    ALLOW is a fixpoint under every posture: a check that concluded ALLOW is never turned into an
    objection, so a posture can only relax or redirect a real flag, never manufacture one. The two
    error postures are DISTINCT: an unrecognized OUTCOME falls open to ALLOW (a well-behaved check
    only emits known tokens, so this branch is unreachable in the spine); an unrecognized POSTURE
    fails CLOSED to the STRICT branch, honoring the raw outcome unchanged (never a silent ALLOW).

    `permission_mode` (D6, optional, additive): when `is_oversight_clamped(permission_mode)`,
    `posture_value` is IGNORED and the STRICT rule applies instead -- see the module-level
    comment above `_REDUCED_OVERSIGHT_MODES` for why softening in these two modes is unsafe.

    `layer` (meta-layer immunity, additive; default "object" preserves every existing fold
    byte-for-byte): the `Check.layer` axis from `makoto/registry.py`. A `layer="meta"`
    check's ONLY possible trigger is tampering with Makoto's own audit/enforcement machinery,
    so a permissive posture must not be able to suppress it -- the posture knob is part of the
    very machinery a meta check guards. Rule: a meta BLOCK never softens below ASK. Concretely,
    under LOOSE (BLOCK->ADVISE) and SILENT (BLOCK->ALLOW) a meta BLOCK is floored at ASK
    instead; STRICT and ASK already yield >= ASK, and the oversight clamp above already returns
    the raw BLOCK. Object-layer folds are untouched, and only a raw BLOCK is floored -- a meta
    ASK/ADVISE folds by the ordinary rules (the docstring'd contract is exactly "a meta BLOCK
    never softening below ASK", nothing broader).
    """
    if outcome not in _OUTCOMES:
        return ALLOW
    if outcome == ALLOW:
        return ALLOW
    if is_oversight_clamped(permission_mode):
        return outcome                      # forced STRICT: honor the raw outcome unchanged
    if outcome == BLOCK and layer == "meta" and posture_value in (LOOSE, SILENT):
        return ASK          # meta floor: tamper detection never softens below ASK
    if posture_value == SILENT:
        return ALLOW
    if posture_value == LOOSE:
        return ADVISE if outcome == BLOCK else outcome
    if posture_value == ASK_POSTURE:
        return ASK if outcome in (BLOCK, ASK) else outcome
    # STRICT (and the fail-closed default): honor the raw outcome unchanged.
    return outcome


# ==== Section 2: wire (former verdict/wire.py) — original module docstring: ====
# Makoto :: wire.py — the wire protocol seam (posture enum -> host JSON).
#
# Intent: Be the ONE zero-inspection lookup table from ``posture.py``'s folded posture enum
# (``BLOCK | ASK | ADVISE | ALLOW``) to a Claude Code hook response, re-deriving NO policy and
# failing OPEN on every renderer path (a lookup miss returns ``{}`` — never an exception).
#
# SPEC-5 (Makoto absorbs Assay): this module is a copy-BY-SHAPE of Assay's
# ``adapters/hook_bridge.py`` (its ``_PRE_WIRE``/``_STOP_WIRE``/``_POST_WIRE`` tables and renderers,
# ``hook_bridge.py:148-222``) — the logic and doc intent are ported, but this file does NOT import
# from ``assay`` (repo boundary law: shapes are copied, never imported, across the faculties; Assay
# retires later, so Makoto's wire module must stand alone).
#
# ZERO INSPECTION. ``dispatch_posture`` maps a live edge name to the matching table and looks the
# folded posture up in it — one table per hook edge, keyed by the enum, no branching on message /
# locus / arm. The posture carries no free-text reason (``posture.apply`` folds context away), so the
# human-facing reason is a CONSTANT per posture, declared here beside its wire words — not a value
# re-derived from check state. A ``posture.Decision``'s ``.detail`` coordinate, when present,
# overrides the constant wording (see ``_detail``).
#
# RETURN SHAPE. ``dispatch_posture(edge, posture, hook_name) -> dict`` returns the CC hook response
# body only (no exit-code tuple — Task 1's public seam is a pure body renderer; the process's exit
# code is the caller's concern, wired at Task 8's dispatch integration). This is the seam Task 8's
# ``dispatch.py`` cutover calls.
#
# WIRE TABLES, one per edge:
#   * Pre  (``_PRE_WIRE``):  BLOCK -> deny, ASK -> ask, ADVISE -> allow + ``additionalContext``,
#     ALLOW -> absent (``{}`` — proceed untouched).
#   * Stop / SubagentStop (``_STOP_WIRE``): BLOCK -> block the stop (``decision: "block"``, echoing
#     whichever of the two edges actually fired via ``hookEventName``); everything else -> ``{}``.
#   * Post (``_POST_WIRE``): ADVISE -> allow + ``additionalContext``; everything else -> ``{}`` — the
#     audit edge is otherwise silent and NEVER emits a deny/block key, regardless of posture.
#
# AGNOSTIC: no I/O, no env read, stdlib only. FAIL-OPEN: an edge name / posture the tables don't
# recognize renders ``{}`` (no objection) rather than raising.


from typing import Callable, Dict

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
    BLOCK: _pre_deny,
    ASK: _pre_ask,
    ADVISE: _pre_advise,
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
    BLOCK: _stop_block,
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
    ADVISE: _post_advise,
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
    response body, re-deriving no policy. This is what Task 8's ``dispatch.py`` cutover calls.

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


# ==== Section 3: recheck (former verdict/recheck.py) — original module docstring: ====
# Certificates that recheck a claimed verdict against its raw fold inputs.


from dataclasses import dataclass

from makoto.vocab import Finding


@dataclass(frozen=True)
class VerdictCertificate:
    """Raw verdict inputs paired with the outcome and detail they claim."""

    findings: tuple[Finding, ...]
    mode: str
    permission_mode: str | None
    claimed_outcome: str
    claimed_detail: str


def recheck_certificate(certificate: VerdictCertificate) -> tuple[str, str]:
    """Reconstruct and verify a certificate's claimed ``(outcome, detail)``.

    A mismatch raises deliberately instead of following ``dispatch.py``'s per-check
    ``try/except: continue`` fail-open convention. A broken individual check must not suppress
    other checks, but a fold-aggregator mismatch invalidates the verdict itself and is therefore
    not a per-check fault that can safely be ignored.
    """
    # Local so the later F4 wiring can import this module from dispatch without an import cycle.
    from makoto.dispatch import _finding_layer, _jit_hint, _worst_finding

    worst = _worst_finding(list(certificate.findings))
    if worst is None:
        reconstructed = (ALLOW, "")
    else:
        outcome, finding = worst
        detail = finding.message
        if outcome == BLOCK:
            hint = _jit_hint(finding)
            if hint:
                detail = f"{detail}\n{hint}"
        folded = apply(
            Decision(outcome, detail),
            certificate.mode,
            permission_mode=certificate.permission_mode,
            layer=_finding_layer(outcome, finding, certificate.mode,
                                 certificate.permission_mode),
        )
        reconstructed = (str(folded), getattr(folded, "detail", ""))

    claimed = (certificate.claimed_outcome, certificate.claimed_detail)
    if reconstructed != claimed:
        raise ValueError(
            f"certificate claim does not match reconstruction: "
            f"claimed={claimed!r}, reconstructed={reconstructed!r}"
        )
    return reconstructed
