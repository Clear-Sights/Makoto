"""makoto.core._declaredverifiers — the repository's own statement of which programs verify it.

WHY THIS EXISTS. `checks/spec.py` recognises a verifier two ways, and both are
name-shaped:

  * `_LEAD_RUNNER_RX` — a closed vocabulary of foreign-ecosystem runner NAMES (`pytest`,
    `go test`, `npm test`). Unambiguous, so it may BLOCK. Blind to anything not on the list.
  * `_LOCAL_SCRIPT_VERIFIER_RX` — a heuristic over FILE NAMING (`gate|check|verify|...`).
    Its own docstring states both failure directions: it cannot see `python3 eval/replay.py`
    (a real verifier — this repository's own corpus replay — whose name says nothing), and it
    matches `check-deploy.sh`, which may well be a deploy step. Because a name is not an
    interface, that tier may only ADVISE.

Neither hole can be closed by adding more names. A third source closes both: the repository
SAYING which of its own programs are verifiers. A declaration is not a guess about a name, it is
a statement by the only party that knows, so a mask on a DECLARED verifier is unambiguous
evidence and may block — exactly the standard `_is_runner_command`'s own docstring already sets
for spending a deny ("only ever spent on a token whose runner-hood is unambiguous").

THE DECLARATION. A file named `makoto.toml` at the repository root (the `cwd` the host reports
with the event), carrying one array:

    # Programs this repository verifies itself with.
    verifiers = ["eval/replay.py", "gates.sh", "tools/render_checks.py"]

MATCHED EXACTLY, never by pattern: a command's leading token is declared iff the token as
written is listed, or its trailing path component equals a listed entry's trailing path
component. No globs, no substrings, no word-stems — the whole point is to stop guessing at
names, so this must not smuggle in a smaller guess of its own.

THE DECLARATION NEVER SILENCES ANYTHING. It is consulted BEFORE the naming heuristic and adds a
blocking tier; it cannot switch the heuristic off. A declaration that could suppress findings
would be a self-mute lever an agent could pull by declaring one harmless program — the shape
`checks/spec.py` exists to catch. So this file can only ever make makoto stricter,
which is also why an unreadable or malformed declaration is answered with "nothing is declared"
(fail-open, matching every other loader in this package): the worst that costs is a block that
degrades to the heuristic's advisory, never a block invented out of a bad parse.

COST. One `os.path.isfile` plus one small read per (root, process), memoised — every later
segment of the same command, and every later command in the process, is a frozenset membership
test. The dispatcher forks per event, so the read is paid at most once per event that reaches the
masking branch at all, and never by an event whose command carries no mask keyword (the catalog's
keyword pre-filter runs first).
"""
from __future__ import annotations

import os
from functools import lru_cache

DECLARATION_BASENAME = "makoto.toml"
DECLARATION_KEY = "verifiers"

_EMPTY: tuple[frozenset, frozenset] = (frozenset(), frozenset())


def _tail(word: str) -> str:
    """Trailing path component of a declared or observed path word.

    Deliberately NOT `core._shell._basename`: that one splits on "/" only, which is right for an
    argv word, while a declaration is typed by an operator who may have used "\\".
    """
    return word.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


@lru_cache(maxsize=16)
def declared_verifiers(root: str) -> tuple[frozenset, frozenset]:
    """`(tokens, tails)` declared by `root`'s `makoto.toml`, or two empty sets.

    Memoised per root: the file is read once per process per root. Call `cache_clear()` when a
    test writes a declaration under a root this process has already asked about.
    """
    if not root:
        return _EMPTY
    path = os.path.join(root, DECLARATION_BASENAME)
    try:
        if not os.path.isfile(path):
            # isfile, not exists: a FIFO or device node planted at this path would block the read
            # and wedge the hook -- the same guard selfWiredCheck._default_plugin_fs_read carries.
            return _EMPTY
        import tomllib
        with open(path, "rb") as handle:
            # Binary by tomllib's own contract: it decodes UTF-8 itself, so the platform default
            # encoding is never consulted here (tests/test_encoding_is_stated.py's subject).
            data = tomllib.load(handle)
    except Exception:
        return _EMPTY
    if not isinstance(data, dict):
        return _EMPTY
    listed = data.get(DECLARATION_KEY)
    if not isinstance(listed, (list, tuple)):
        return _EMPTY
    tokens = frozenset(v for v in listed if isinstance(v, str) and v.strip())
    return (tokens, frozenset(_tail(v) for v in tokens))


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
