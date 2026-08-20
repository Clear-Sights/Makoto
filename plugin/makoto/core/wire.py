"""makoto.core.wire -- the byte boundary: raw hook stdin -> a str the rest of Makoto can persist.

ONE domain: everything between "the host wrote bytes into our pipe" and "dispatch has a Python
str". Stdlib-only, no makoto-internal imports, so anything may depend on it.

WHY THIS MODULE EXISTS (the live crash it closes)
`dispatch.main()` opened with `sys.stdin.read()`. Under the C/POSIX locale -- which is what a hook
subprocess actually gets, since no interactive shell has exported LANG for it -- CPython enables
UTF-8 mode (PEP 540) and gives `sys.stdin` the `surrogateescape` error handler. Any byte the host
wrote that is not valid UTF-8 therefore does not raise and does not get replaced: it is smuggled in
as a LONE SURROGATE, one per bad byte, `0xDC00 + byte`.

That str parses as JSON, routes, and reaches `_ingest_event`, where sqlite3 encodes bind
parameters to UTF-8 STRICTLY and raises::

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\udc9d'
                        in position 143: surrogates not allowed

`\\udc9d` is byte 0x9D -- a CP1252/Latin-1 byte in a file being written, or a multi-byte sequence
the host truncated. `main()`'s catch-all then recorded a `loud-allow` fact and returned 0, so the
tool call proceeded WITH NO CHECK HAVING RUN. Measured live: 30 such loud-allows in one day, every
one of them Makoto failing open on its own bug. A gate that vanishes on malformed input was never
a gate on that input.

The same byte reaches the sibling plugins through the same door and they disagree about what it
means -- Ward's `ast.parse` fails and it hard-DENIES a benign file with "cannot be parsed
independently"; Gyroscope's `derive_id` raises inside a per-clause `except Exception: continue`
and the clause silently abstains. Three plugins, one bad byte, three different verdicts, none of
them about the pending action. That is why the fix is at the boundary and not at any one crash
site: a lone surrogate must never exist downstream of this module.

WHAT THIS IS NOT
Not a sanitizer for hostile input and not a re-encoder. It makes exactly one guarantee -- no
surrogate code point survives -- and it makes that guarantee ON THE RECORD: both entry points
report how many code points they replaced, so "the payload was repaired" is a fact a caller can
log rather than a silent rewrite of the agent's evidence.
"""
from __future__ import annotations

import re
import sys
from typing import Any

# U+FFFD REPLACEMENT CHARACTER: the standard "a code point was here and it was not representable"
# marker. Chosen over dropping the code point so byte offsets in a payload stay roughly meaningful
# and so a repaired region is visible in the log rather than invisible.
REPLACEMENT = "�"

# The whole surrogate range, high and low alike. The byte decode below routes its own
# surrogates straight back through here; this regex also closes the OTHER door -- a well-formed
# UTF-8 payload whose JSON *text* contains an unpaired `\ud89d` escape, which `json.loads`
# faithfully turns into a real lone surrogate. One of those doors is the host's encoding and the
# other is the host's JSON writer; both end in the same sqlite3 raise, so both are closed here.
_SURROGATE_RX = re.compile("[\ud800-\udfff]")


def scrub_text(text: str) -> tuple[str, int]:
    """Return (text with every surrogate code point replaced, number replaced).

    Fast path is a search, not a substitution: the overwhelmingly common case is a clean payload,
    and this runs on every hook event of every session.
    """
    if not _SURROGATE_RX.search(text):
        return text, 0
    # `subn` returns (result, count) from ONE pass. The earlier form ran `sub` and then
    # `findall`, scanning the damaged text twice and building a throwaway list of every
    # match to get a number `subn` already had. Measured 2.0x on the repair path.
    return _SURROGATE_RX.subn(REPLACEMENT, text)


def scrub(value: Any) -> tuple[Any, int]:
    """Recursively scrub every str inside a parsed JSON value; return (value, total replaced).

    Dict KEYS are scrubbed too. A surrogate in a key is rarer than one in a value but reaches the
    same encoder, and a key that cannot be serialized fails the whole row rather than one field.

    Containers are rebuilt only when something below them actually changed, so a clean payload --
    the normal case -- comes back as the same objects it went in as.
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
                    # Scrubbing is NOT injective on keys: every surrogate becomes the same U+FFFD,
                    # so two genuinely different damaged keys collapse onto one name and the plain
                    # assignment below dropped the earlier one's VALUE on the floor without a word.
                    # `wire.scrub({"\ud800": 1, "\ud801": 2})` returned `({'\ufffd': 2}, 2)` -- a
                    # count of 2 repairs next to a dict that had lost a field. This module's one
                    # promise is that repair is on the record; silently deleting a field is the
                    # opposite of that, and the field could be `tool_input`. The suffix keeps both
                    # values reachable and keeps the collision visible in the persisted row.
                    # Tested against `value` as well as `out` so a CLEAN key later in the dict
                    # keeps its own name rather than being overwritten by a repaired one.
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

    Returns (text, replaced). Reading `.buffer` rather than the text wrapper is the load-bearing
    part: it takes the decode away from whatever error handler the ambient locale happened to
    install. A stream without a `.buffer` (a host that hands us text) is read as text and scrubbed
    instead -- same guarantee, one door further in.
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        try:
            data = buffer.read()
        except (AttributeError, ValueError, OSError):
            # A closed or non-binary buffer: fall through to the text path rather than making the
            # hook's first act a crash.
            data = None
        # `is not None`, not a truthiness test, and the reason it is a separate statement rather
        # than an `else:` on the try: a NON-BLOCKING stdin's `read()` returns None (not b"") when
        # no data is ready, and handing that to `_decode_counting` is an AttributeError on
        # `.decode` -- a crash on the read path, which is the one path that must not crash. b"" is
        # a real answer (an empty envelope) and takes the decode path as it should.
        if data is not None:
            return _decode_counting(data)
    # Same BOM rule as the byte path: a host that hands us TEXT can hand us a leading U+FEFF
    # too, and json.loads refuses it ("Unexpected UTF-8 BOM") -- see _decode_counting.
    return scrub_text((sys.stdin.read() or "").lstrip("\ufeff"))


def _decode_counting(data: bytes) -> tuple[str, int]:
    """Decode `data` as UTF-8, returning (text, number of undecodable BYTES repaired).

    Strict first, on purpose: a clean payload reports zero repairs by construction, so the count can
    never be inflated by a U+FFFD the host legitimately sent. A number that cries wolf gets ignored,
    and takes the next real one with it.
    """
    # "utf-8-sig", not "utf-8": a UTF-8 BOM (b"\xef\xbb\xbf") on the envelope strict-decodes
    # to a leading U+FEFF that json.loads then REFUSES ("Unexpected UTF-8 BOM (decode using
    # utf-8-sig)"), so a structurally perfect payload took the unparseable_payload loud-allow --
    # every check disabled for that call, and the recorded reason ("stdin was not valid JSON")
    # false. state/ledger.py already reads its own files with utf-8-sig for exactly this class;
    # this is the one remaining door in the family that never got the pattern. A BOM is a
    # legitimate encoding artifact, not damage, so it does not count as a repair.
    try:
        return scrub_text(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        pass
    # `surrogateescape`, then scrub -- NOT `errors="replace"`.
    #
    # `replace` emits ONE U+FFFD per malformed RUN, so a truncated three-byte sequence like
    # b"\xe2\x82" (two undecodable bytes) reported 1, and the field is called "bytes repaired".
    # An observability number whose name does not match its arithmetic is the kind of thing that
    # gets trusted right up until someone reconciles two counts and cannot.
    #
    # `surrogateescape` maps each undecodable BYTE to exactly one lone surrogate, so counting the
    # surrogates counts bytes -- which is what the field says. Scrubbing them immediately is what
    # keeps the module's one guarantee: no surrogate leaves here. It also retires the
    # `data.count(b"\xef\xbf\xbd")` correction entirely, since surrogateescape never touches a
    # U+FFFD the host legitimately sent.
    return scrub_text(data.decode("utf-8-sig", errors="surrogateescape"))


def harden_stderr() -> None:
    """Pin BOTH outbound streams -- stderr AND stdout -- to a never-raising error handler.

    stderr: every fail-open path in `dispatch` ends in a `print(..., file=sys.stderr)` that
    interpolates an exception message. When the exception is itself about an unencodable character,
    that print can raise -- turning the on-the-record fact into a second, unrecorded crash and
    taking the hook's exit code with it. The reporting path must be the one thing that cannot fail.
    CPython already defaults stderr to `backslashreplace`, so this leg is belt-and-braces: it earns
    its keep only when the host, or a test harness, handed us a stricter stderr.

    stdout is the leg that is actually load-bearing, despite the name this function is stuck with
    (`dispatch` calls it by name; a module does not get to rename its own callers). stdout carries
    the ONE decision object, and CPython does NOT default it to a forgiving handler: `strict`
    ordinarily, and `surrogateescape` under the PEP 540 UTF-8 mode a hook subprocess actually runs
    in. Both defaults break the one-well-formed-JSON-object-on-stdout contract if a surrogate ever
    reaches that encoder -- `strict` raises PART-WAY THROUGH the write and leaves a truncated
    object on the pipe, and `surrogateescape` writes the original undecodable BYTE straight back
    out, leaving an object the host's UTF-8 JSON reader cannot decode. `replace` yields a U+FFFD
    and a well-formed object in both cases. Nothing should ever reach here carrying a surrogate --
    that is this module's whole promise -- so this is the floor under the promise, not a substitute
    for keeping it.

    Best-effort: `reconfigure` needs a TextIOWrapper, and a stream that is something else is left
    alone rather than replaced.
    """
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
