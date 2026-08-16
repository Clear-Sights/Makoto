# 0042: phantomCitation's jscpd clone flag

Date: 2026-07-09

## Relocated design history

From `phantomCitation.py`, above `predicate()`:

```text
jscpd note (2026-07-09): flagged as a clone against fabricatedCommitSha.py. Verified: the
matched span is the fixed dispatcher entrypoint signature `predicate(*, current_event: dict,
history: list, pattern: Check, conn=None) -> Optional[Finding]` -- byte-identical across 9
check modules (grep '^def predicate(' checks/*.py) -- plus a coincidental preceding
`return False` from this file's own unrelated `_within_governed_tree` helper. A
dispatcher-invoked entrypoint's signature is a structural contract, not extractable logic;
the two functions' bodies do unrelated things (SHA-fabrication detection vs.
citation-allowlist path scoping).
```

## Decision

The duplication jscpd reports between `phantomCitation.py` and `fabricatedCommitSha.py` is
accepted as-is; neither module is refactored to remove it.

## Rationale

The matched span is the dispatcher entrypoint signature, which is byte-identical across every
predicate module by contract. Collapsing it would mean changing a structural interface to
satisfy a duplication metric, while the two functions' bodies share nothing.

## Alternatives considered

Extracting a shared helper for the "clone" (rejected: there is no shared logic — only a shared
signature — and the entrypoint signature is a contract the dispatcher relies on).
