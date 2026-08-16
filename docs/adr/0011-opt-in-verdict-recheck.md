# 0011: Opt-in verdict recheck

Date: 2026-08-16

## Relocated design history

From `_recheck_certificate_enabled()`:

```text
Opt-in (OFF by default, mirroring the MAKOTO_DISABLE_* switch parsing): when
MAKOTO_RECHECK_CERTIFICATE=1, `_emit_decision` re-verifies its own folded verdict via
`makoto.verdict.recheck.recheck_certificate` before writing it to the wire. A mismatch
RAISES (recheck.py's deliberate not-fail-open rule) — which is why this is opt-in: with the
flag unset, production hook behavior is provably unchanged (this predicate is the only new
code on the hot path, and it cannot raise).
```
