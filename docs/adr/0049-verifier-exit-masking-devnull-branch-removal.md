# 0049: Verifier exit-masking scoped to exit codes only

Date: 2026-06-02

## Relocated design history

From `content.verifier_exit_masking`'s module docstring:

```text
SCOPED to exit-code masking ONLY (2026-06-02 graduation). The `2>/dev/null` / `&>/dev/null` branch
was REMOVED: stream redirection does NOT alter `$?` (`sys.exit(7) 2>/dev/null` still exits 7) — every
runner in _LEAD_RUNNER_RX signals failure via a nonzero exit, so silencing stderr cannot turn a real
failure into a green. The devnull branch detected honest stderr-noise suppression, not failure-masking
(a category error), and was the predicate's only false-positive source on the real corpus (2 fires,
both honest diagnostics). Removing it drives corpus-FP to 0 → graduated to BLOCKING.
```

## Decision

The check's scope is exit-code masking only (`|| true`, `; true`, `|| :`, `set +e`). Stream
redirection is out of scope.

## Rationale

Redirecting stderr does not change `$?`, so it cannot convert a real failure into a green — the
thing this check exists to catch. The redirection arm was therefore a category error: it detected
honest diagnostic-noise suppression, and it was the predicate's only false-positive source on the
real corpus (2 fires, both honest). Removing it took corpus-FP to 0, which is what allowed the
check to graduate to a BLOCKING posture.

## Alternatives considered

Keeping the `2>/dev/null` / `&>/dev/null` branch and suppressing its false positives with
additional narrowing — rejected, because the branch had no true-positive class to protect: no
runner in `_LEAD_RUNNER_RX` signals failure through stderr alone.
