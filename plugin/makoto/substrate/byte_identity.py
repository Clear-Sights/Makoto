"""makoto.substrate.byte_identity — an op-restricted byte-identity wrapper, the NEUTRAL LEAF home of
``ByteIdentity`` (copied by shape from the makoto-dev ancestor, CANON-PORT-1).

``ByteIdentity`` makes a content-MEANING read UNCONSTRUCTIBLE rather than merely discouraged: it
exposes ONLY ``==`` / ``len`` / ``hash``. There is NO ``__contains__``, ``__iter__``,
``__getitem__``, ``.lower()``, ``.search`` or any str-coercion path, so ``"tok" in bi`` /
``bi.lower()`` / ``re.search(rx, bi)`` / ``bi[0]`` all RAISE — the content-MEANING read cannot be
WRITTEN in the consumer body, so it cannot drift in.

Equality is WHITESPACE-NORMALIZED byte identity: the blob is collapsed to its
``" ".join(s.split())`` canonical form at construction, so a trailing newline, a double space, or a
collapsed run is cosmetic (the same check), while a genuine token difference (a narrowed/swapped
command, a one-byte-off edit) is a mismatch. ``len`` is a count over that canonical form (no token
meaning leaks); ``hash`` is consistent with ``==``. Stdlib-only, no LLM, no HTTP."""
from __future__ import annotations


def _canon(blob: object) -> str:
    """The whitespace-normalized canonical form: ``""`` for None, else
    ``" ".join(str(blob).split())`` (collapse all whitespace runs, strip the ends).

    Bytes-LIKE blobs (``bytes``/``bytearray``/``memoryview``) canonicalize by CONTENT, not by
    ``repr()``, so identical bytes compare equal whatever container carried them. The decode is
    ``surrogateescape`` (injective per byte), so non-UTF-8 content canonicalizes deterministically
    instead of raising out of the constructor and silently disabling the caller's check."""
    if blob is None:
        return ""
    if isinstance(blob, (bytes, bytearray, memoryview)):
        blob = bytes(blob).decode(errors="surrogateescape")
    return " ".join(str(blob).split())


class ByteIdentity:
    """A CONTENT blob exposing ONLY whitespace-normalized byte-identity equality, length, and hash.

    Permitted (agnostic): ``a == b`` (whitespace-normalized byte equality), ``len(a)`` (a count
    over the canonical form), ``hash(a)``.
    UNCONSTRUCTIBLE (a content-MEANING read): ``"x" in a``, ``a.lower()``, ``a[0]``, ``list(a)``,
    ``re.search(rx, a)`` — every one RAISES, never silently degrades."""

    __slots__ = ("_canon", "_is_none")

    def __init__(self, blob: object) -> None:
        # None (an ABSENT content) is tracked apart from the empty canonical form: a history row
        # carrying `"content": null` must not read as identical to a legitimate empty/whitespace-
        # only write, or an A->B->"" sequence spuriously blocks as a revert of the null row.
        self._is_none = blob is None
        self._canon = _canon(blob)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ByteIdentity):
            return self._is_none == other._is_none and self._canon == other._canon
        if isinstance(other, (str, bytes)):
            return not self._is_none and self._canon == _canon(other)
        return NotImplemented

    def __len__(self) -> int:
        return len(self._canon)

    def __hash__(self) -> int:
        # The BARE canonical form, so `hash(bi) == hash(canonical_str)` and a set/dict keyed on
        # ByteIdentity can be probed with the raw canonical string (hash consistent with the
        # `str` arm of `__eq__` for canonical inputs).
        return hash(self._canon)

    def __bool__(self) -> bool:
        # Constant True: `__len__` alone would leak content EMPTINESS through `if bi:` -- an
        # operation the class advertises as not on the type.
        return True

    def __repr__(self) -> str:
        return f"ByteIdentity(len={len(self._canon)})"

    # NO __contains__, __iter__, __getitem__, __str__-as-content, lower/upper/find/etc.: a
    # content-meaning read is not on the type, so it cannot be constructed.