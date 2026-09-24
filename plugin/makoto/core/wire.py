"""makoto.core.wire -- the byte boundary: raw hook stdin -> a str the rest of Makoto can persist.

ONE domain: everything between "the host wrote bytes into our pipe" and "dispatch has a Python
str". Stdlib-only, no makoto-internal imports, so anything may depend on it.

Why: under the C/POSIX locale a hook subprocess actually runs in, CPython's UTF-8 mode gives
`sys.stdin` the `surrogateescape` error handler, so any byte the host wrote that is not valid
UTF-8 is smuggled in as a LONE SURROGATE (`0xDC00 + byte`) instead of raising or being replaced.
That string then reaches sqlite3, which encodes bind parameters to UTF-8 STRICTLY and raises --
and the caller's catch-all used to record a loud-allow and return 0, letting the tool call
proceed with no check having run. A gate that vanishes on malformed input was never a gate on
that input, so a lone surrogate must never exist downstream of this module.

Not a sanitizer for hostile input and not a re-encoder: the one guarantee is that no surrogate
code point survives, made ON THE RECORD -- both entry points report how many code points they
replaced, so a repair is a logged fact, never a silent rewrite of the agent's evidence.
"""
from __future__ import annotations

import re
import sys
from typing import Any

# U+FFFD: chosen over dropping the code point so byte offsets stay roughly meaningful and a
# repaired region is visible in the log rather than invisible.
REPLACEMENT = "�"

# The whole surrogate range. Closes both doors: the byte decode below routing its own surrogates
# back through here, and a well-formed UTF-8 payload whose JSON text contains an unpaired escape
# that json.loads turns into a real lone surrogate.
_SURROGATE_RX = re.compile("[\ud800-\udfff]")


def scrub_text(text: str) -> tuple[str, int]:
    """(text with every surrogate code point replaced, number replaced).

    Fast path is a search, not a substitution, since a clean payload is the common case and this
    runs on every hook event.
    """
    if not _SURROGATE_RX.search(text):
        return text, 0
    return _SURROGATE_RX.subn(REPLACEMENT, text)


def scrub(value: Any) -> tuple[Any, int]:
    """Recursively scrub every str inside a parsed JSON value; return (value, total replaced).

    Dict keys are scrubbed too. Containers are rebuilt only when something below them actually
    changed, so a clean payload comes back as the same objects it went in as.
    """
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        out, total = {}, 0
        for k, v in value.items():
            if isinstance(k, str):
                k, n = scrub_text(k)
                total += n
                if n and (k in out or k in value):
                    # Scrubbing is not injective on keys: two different damaged keys can collapse
                    # onto the same U+FFFD name, silently dropping the earlier one's value. The
                    # suffix keeps both values reachable and the collision visible in the row.
                    # Checked against `value` too so a clean key later in the dict keeps its own
                    # name instead of being overwritten by a repaired one.
                    suffix = 2
                    while f"{k}~{suffix}" in out or f"{k}~{suffix}" in value:
                        suffix += 1
                    k = f"{k}~{suffix}"
            v, n = scrub(v)
            total += n
            out[k] = v
        return (out, total) if total else (value, 0)
    if isinstance(value, list):
        items, total = [], 0
        for item in value:
            item, n = scrub(item)
            total += n
            items.append(item)
        return (items, total) if total else (value, 0)
    return value, 0


def read_stdin() -> tuple[str, int]:
    """Read the hook envelope off stdin as BYTES and decode it to a surrogate-free str.

    Returns (text, replaced). Reading `.buffer` rather than the text wrapper takes the decode
    away from whatever error handler the ambient locale installed. A stream without a `.buffer`
    is read as text and scrubbed instead -- same guarantee, one door further in.
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        try:
            data = buffer.read()
        except (AttributeError, ValueError, OSError):
            data = None  # closed/non-binary buffer: fall through to the text path
        # A non-blocking stdin's `read()` can return None (not b""); handing that to
        # `_decode_counting` would raise on `.decode`, so check explicitly rather than `else:`.
        if data is not None:
            return _decode_counting(data)
    # A host that hands us TEXT can still hand a leading U+FEFF, which json.loads refuses.
    try:
        return scrub_text((sys.stdin.read() or "").lstrip("\ufeff"))
    except (AttributeError, TypeError, ValueError, OSError):
        return "", 0


def _decode_counting(data: bytes) -> tuple[str, int]:
    """Decode `data` as UTF-8, returning (text, number of undecodable BYTES repaired).

    Strict first: a clean payload reports zero repairs by construction, never inflated by a
    U+FFFD the host legitimately sent.
    """
    # "utf-8-sig", not "utf-8": a UTF-8 BOM strict-decodes to a leading U+FEFF that json.loads
    # then refuses. A BOM is a legitimate encoding artifact, not damage, so it is not a repair.
    try:
        return scrub_text(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        pass
    # `surrogateescape`, not `errors="replace"`: replace emits one U+FFFD per malformed RUN
    # (undercounting multi-byte runs), while surrogateescape maps each bad BYTE to one lone
    # surrogate, so counting surrogates counts bytes -- matching the field's name.
    return scrub_text(data.decode("utf-8-sig", errors="surrogateescape"))


def harden_stderr() -> None:
    """Pin both stderr and stdout to a never-raising error handler.

    stderr's fail-open prints can themselves raise on an unencodable character, turning an
    on-the-record fact into a second, unrecorded crash. stdout is the load-bearing leg: it
    carries the one decision object, and neither `strict` nor `surrogateescape` (CPython's
    defaults) keep the one-well-formed-JSON-object-on-stdout contract if a surrogate reaches
    that encoder -- `replace` yields a U+FFFD and a well-formed object either way.

    Best-effort: `reconfigure` needs a TextIOWrapper; any other stream is left alone.
    """
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.reconfigure(errors="backslashreplace" if stream is sys.stderr else "replace")
        except (AttributeError, TypeError, ValueError, OSError):
            pass
