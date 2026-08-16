# 0032: Whole-suite green-claim signal relocated to substrate.claims

Date: 2026-06-09

## Relocated design history

From `makoto/checks/falseGreenClaim.py`:

```text
The prose half (the whole-suite green-claim signal) RELOCATED to substrate.claims.whole_suite_pass_claim
(consolidation T2.2, 2026-06-09): truthiness-identical pure relocation; the second consumer is
gate.stale_pass, which additionally uses the returned Match's POSITION for its teeth window.
```
