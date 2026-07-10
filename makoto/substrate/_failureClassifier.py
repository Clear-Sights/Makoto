"""makoto.substrate._failureClassifier -- transient-vs-deterministic failure classification, the
ship-bar Fable named for D1 (identical-retry interdiction, docs/DEFERRED.md). Two Fable
consultations converged on this exact requirement: a BLOCK-tier check denying a retry must never
deny a LEGITIMATE re-poll of a transient failure (a timeout, a 5xx, "still running"), so this
classifier is conservative -- it fails toward UNCERTAIN (None), never toward "assume
deterministic", whenever the signal is ambiguous. "If the runtime cannot discriminate, the
honest outcome is to cut or defer the check, not demote it to advisory" (Fable, verbatim) -- this
module is what makes discrimination possible at all; identicalRetryInterdiction.py refuses to
fire on anything but a confident True.

Package plumbing (underscore-prefixed, like _canonAtoms.py/_primitives.py) -- shared classification
logic, not itself a detector module; checks._loader's scan skips it.
"""
from __future__ import annotations

import re
from typing import Optional

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
