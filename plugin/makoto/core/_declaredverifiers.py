"""makoto.core._declaredverifiers — the repository's own statement of which programs verify it.

WHY THIS EXISTS. `checks/spec.py` recognises a verifier two ways, both name-shaped:

  * `_LEAD_RUNNER_RX` — a closed vocabulary of foreign-ecosystem runner names (`pytest`,
    `go test`, `npm test`). Unambiguous, so it may block. Blind to anything not listed.
  * `_LOCAL_SCRIPT_VERIFIER_RX` — a heuristic over file naming (`gate|check|verify|...`). It
    cannot see `python3 eval/replay.py` (a real verifier whose name says nothing) and matches
    `check-deploy.sh`, which may well be a deploy step. A name is not an interface, so this tier
    may only advise.

Neither hole closes by adding more names. A declaration is not a guess about a name, it is a
statement by the only party that knows, so a mask on a declared verifier is unambiguous and may
block.

THE DECLARATION. A file named `makoto.toml` at the repository root, carrying one array:

    verifiers = ["eval/replay.py", "gates.sh", "tools/render_checks.py"]

Matched exactly, never by pattern: a command's leading token is declared iff the token as
written is listed, or its trailing path component equals a listed entry's trailing path
component. No globs, no substrings, no word-stems.

THE DECLARATION NEVER SILENCES ANYTHING. It is consulted before the naming heuristic and only
adds a blocking tier; it cannot switch the heuristic off, which would let an agent self-mute by
declaring one harmless program. An unreadable or malformed declaration reads as "nothing is
declared" (fail-open): the worst that costs is a block degrading to advisory, never a block
invented from a bad parse.

COST. One `os.path.isfile` plus one small read per (root, process), memoised — every later
segment of the same command, and every later command in the process, is a frozenset membership
test.
"""
from __future__ import annotations

import os
from functools import lru_cache

DECLARATION_BASENAME = "makoto.toml"
DECLARATION_KEY = "verifiers"
# The opt-in key the dispatch-discipline rows gate on -- same file, same reader.
DISPATCH_KEY = "dispatch"

_EMPTY: tuple[frozenset, frozenset] = (frozenset(), frozenset())


def _tail(word: str) -> str:
    """Trailing path component of a declared or observed path word.

    Deliberately not `core._shell._basename`: that splits on "/" only, right for an argv word,
    while a declaration may be typed by an operator using "\\".
    """
    return word.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


@lru_cache(maxsize=16)
def _declaration(root: str) -> dict:
    """`root`'s `makoto.toml`, decoded once, or `{}`. Memoised per root; call `cache_clear()` after a test writes one."""
    if not root:
        return {}
    path = os.path.join(root, DECLARATION_BASENAME)
    try:
        if not os.path.isfile(path):
            # isfile, not exists: a FIFO or device node here would block the read and wedge the hook.
            return {}
        import tomllib
        with open(path, "rb") as handle:
            # Binary: tomllib decodes UTF-8 itself, so the platform default encoding is never consulted.
            data = tomllib.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def declared_verifiers(root: str) -> tuple[frozenset, frozenset]:
    """`(tokens, tails)` declared by `root`'s `makoto.toml`, or two empty sets."""
    listed = _declaration(root).get(DECLARATION_KEY)
    if not isinstance(listed, (list, tuple)):
        return _EMPTY
    tokens = frozenset(v for v in listed if isinstance(v, str) and v.strip())
    return (tokens, frozenset(_tail(v) for v in tokens))


declared_verifiers.cache_clear = _declaration.cache_clear


def dispatch_opt_in(root) -> bool:
    """True iff `root`'s `makoto.toml` declares `dispatch = true`. Fail-open: unreadable/absent reads as not opted in."""
    if not isinstance(root, str) or not root:
        return False
    return _declaration(root).get(DISPATCH_KEY) is True


dispatch_opt_in.cache_clear = _declaration.cache_clear


def owner_paths(root) -> tuple:
    """The paths `root`'s `makoto.toml` declares as the owner's hands (`owner_paths = [...]`):
    files and directories the agent must not delete, overwrite or cut. Fail-open: `()`."""
    if not isinstance(root, str) or not root:
        return ()
    listed = _declaration(root).get("owner_paths")
    if not isinstance(listed, (list, tuple)):
        return ()
    return tuple(v.strip() for v in listed if isinstance(v, str) and v.strip())


owner_paths.cache_clear = _declaration.cache_clear


def declares_anything(root) -> bool:
    """True iff `root` declares at least one verifier.

    The whole tier's gate, hoisted so a caller pays ONE memoised probe per invocation instead of
    per shell statement: the common case (no `makoto.toml` anywhere) is then a single
    `os.path.isfile` for the process and a boolean test thereafter.
    """
    return bool(isinstance(root, str) and root and declared_verifiers(root)[0])


def is_declared_verifier(token: str, root) -> bool:
    """True iff `token` is a program that `root`'s own `makoto.toml` declares as a verifier."""
    if not token or not isinstance(root, str):
        return False
    tokens, tails = declared_verifiers(root)
    if not tokens:
        return False
    return token in tokens or _tail(token) in tails
