"""Deterministic check primitives for makoto's update/check engine.

Location is normalized-path EQUALITY (not substring — equality is the fakeexcuse
firewall). Quantity is a number compare. Subject-binding gates retraction reasons.
Stdlib only; no LLM, no HTTP (Knight-Leveson hot-path invariant).
"""
import os
import re


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
_PATH_EXT = (
    r"py|pyi|md|rst|txt|toml|json|jsonl|ndjson|ya?ml|ini|cfg|conf|env|lock|"
    r"sh|bash|zsh|fish|js|jsx|mjs|cjs|ts|tsx|rs|go|rb|java|kt|swift|c|h|hpp|cc|cpp|"
    r"sql|html?|css|scss|sass|xml|csv|tsv|sock|proto|graphql|tf|svg|ipynb|dockerfile"
)
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
