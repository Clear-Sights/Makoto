# 0012: Posture pipeline migration

Date: 2026-08-16

## Relocated design history

From `_emit_decision()`:

```text
This is the real posture pipeline (SPEC-5 Task 8), replacing the old single ad-hoc
"decision":"block" shape that main() used identically for every edge. A BLOCK outcome carries
the finding's message plus its JIT hint (convention text / makoto-allow hatch / conventions
pointer — the same text `_build_decision` used to put in "retry_hint") as the Decision's
`.detail`, so wire.py's per-edge renderer surfaces it in place of its constant reason text.
An ADVISE/ASK outcome at an edge whose table has no entry for it (e.g. ADVISE at Stop/
SubagentStop — everything but BLOCK renders `{}` there by wire.py's own design) — and no
findings at all — both fall through to "write nothing", matching the old None-decision case.
```
