# 0007: Stop gates live rollout

Date: 2026-06-01

## Relocated design history

From `_gates_enabled()`:

```text
Both Stop gates — completion (UNFULFILLED: claimed X produced, X absent) and advance
(SELF-CONTRADICTING: claimed UNIVERSAL completion over an undischarged commitment) — BLOCK
live by default, governed by one switch. Each is validated FP-clean on the 1335-session
honest corpus:
  - completion: production-claim binding drove worst-case FP 9.00% -> self-healing 2.42%,
    TP intact (6/6), contamination canary passing.
  - advance (flipped live 2026-06-01): 0 fires across all 1335 sessions after the
    proposal-menu / code-fence / optional-parenthetical sourcing guards — every residual
    FP traced to a never-built PROPOSAL the AI recommended, never a genuine commitment
    (each of which discharged when its file was touched); TP intact (an undischarged firm
    promise + universal-done still fires), the reason-bound retraction path clears
    legitimately-dropped promises so honest re-prioritization never false-blocks.
MAKOTO_DISABLE_GATES=1 returns BOTH to shadow (still audited, no block) — the single escape
valve if a real-session false-block ever surfaces.
```

From `_evaluate_and_gate()`:

```text
gates. The three Stop gates — completion, advance, and green_claim — block live under the
single _gates_enabled() switch (each validated FP-clean on the 1335-session corpus;
green_claim measured POWERED with real Bash output reconstructed in cert.replay_stop).
All gate fires are always recorded to the audit log, block or not, so any future
real-session FP can still be mined.
```
