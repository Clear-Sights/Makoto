# 0025: Every canon primitive names its release.operator discharge

## Relocated design history

From `_release_clause()` in `canonTimeoutRecur.py`:

```text
`canon_gate` offers the ackblock discharge to EVERY fired primitive — the loop calls
`find_ack_block(cid, ...)` for whatever fired, not just `timeout`. But the affordance was
spelled out only in `timeout`'s hand-written hint, so a fired `canon.recur` told the agent
to "change the input" and nothing else. When the finding was a false positive the agent had
no reachable discharge named anywhere, and every subsequent Stop re-fired the same block
until the rows aged out of the recency window — a mechanism that existed but was invisible
reads exactly like a mechanism that is missing.
```

The structural reason the clause is generated per-id rather than written per-entry — so a primitive
cannot be added to `CANON_SEQ_PRIMITIVES` without carrying the discharge it is already wired to
honor — stays in the source docstring.
