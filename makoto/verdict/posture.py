"""Makoto :: posture.py — the ONE enforcement-posture home (the ``MAKOTO_MODE`` reader).

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


def apply(outcome, posture_value, *, permission_mode=None) -> str:
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
    """
    if outcome not in _OUTCOMES:
        return ALLOW
    if outcome == ALLOW:
        return ALLOW
    if is_oversight_clamped(permission_mode):
        return outcome                      # forced STRICT: honor the raw outcome unchanged
    if posture_value == SILENT:
        return ALLOW
    if posture_value == LOOSE:
        return ADVISE if outcome == BLOCK else outcome
    if posture_value == ASK_POSTURE:
        return ASK if outcome in (BLOCK, ASK) else outcome
    # STRICT (and the fail-closed default): honor the raw outcome unchanged.
    return outcome
