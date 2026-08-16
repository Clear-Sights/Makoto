# Makoto security model

Modeled on Ward's `SECURITY.md` (`/workspace/ward/SECURITY.md`): a guarantee statement, named
non-claims per check family, and the required host/operator boundary, in one file. Unlike Ward
(9 checks, one evaluation contract), Makoto's guarantee and non-claims are scattered across
`makoto/_dispatch.py`'s own docstrings and each check module's own limitation notes; this file
aggregates them with file:line citations. It states nothing the cited code does not already
assert — see `docs/ward-comparison.md` for the research that identified these citations.

## Guarantee

Makoto is a stateful, session-tracking policy filter over Claude Code's hook events
(`PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, `SessionStart`). At `PreToolUse` a matching
BLOCK-posture check cancels the submitted tool call; at `Stop` a matching BLOCK-posture gate
denies the turn from ending. When a check returns no finding, the only conclusion is that the
inspected event/history matched none of the loaded predicates
(`makoto/substrate/_loader.py:1-22`, `makoto/_dispatch.py:1-17`).

Fail-mode is explicitly HYBRID, not fail-closed everywhere: a tamper-shaped payload fails closed
(BLOCK), transient infrastructure trouble (DB lock, import error) fails loud-allow, and every
can't-evaluate case is recorded — never silently dropped (`makoto/_dispatch.py:826-829`,
`_dispatch_fact`, `makoto/_dispatch.py` ~104-118).

Makoto is **not** a reference monitor, a filesystem confinement boundary, or a proof that a
claim is true — only that this session's own recorded evidence does or does not contradict it.
It re-checks only what it has itself ingested (`_ingest_event`) within a bounded rolling window
(`_select_recent`'s 1-hour slice, `makoto/_dispatch.py` ~230-243); it cannot itself go inspect
the live world (curl a port, open a file on disk at check time) — see the per-check non-claims
below.

### Chain self-verification is advisory-first, not enforced

`_self_verify_chain` re-derives the ledger's own tamper-evidence at every dispatch, but ships
**advisory only** — an on-the-record dispatch fact plus a stderr line, never a block — until
real-session soak evidence earns a later, separately-certified flip to block (owner decision,
2026-07-07). A clean or absent/empty chain is silent by `verify_chain`'s own contract
(`makoto/_dispatch.py:125-132`).

### Gate FP/TP posture is corpus-validated, not proof against all inputs

The two live-by-default Stop gates — `gate.completion` (UNFULFILLED: claimed-produced artifact
absent) and `gate.advance` (SELF-CONTRADICTING: claimed universal completion over an
undischarged commitment) — are validated against a 1,335-session honest corpus, not a formal
proof: `gate.completion`'s production-claim binding drove worst-case FP from 9.00% to 2.42%
(TP intact, 6/6); `gate.advance` fired 0 times across all 1,335 sessions after its FP guards,
with every residual pre-guard FP traced to a never-built proposal rather than a genuine
commitment. `MAKOTO_DISABLE_GATES=1` returns both to shadow (still audited, never blocking) as
the single escape valve if a real-session false-block ever surfaces
(`makoto/_dispatch.py:306-321`).

## Named non-claims per check family

Each item names a bypass shape or scope limit its check family deliberately does not catch. An
allow for one of these shapes means only that no loaded predicate matched — never a safety
verdict. Grouped by family; check ids are `load_checks()` ids (see `docs/CHECKS.md`).

### Verifier-weakening (`content.verifier_body_hollowed`, `content.verifier_exit_masking`, `content.verifier_predicate_weakened`)

- `content.verifier_exit_masking` is SCOPED to exit-code masking only (`|| true`, `; true`,
  `set +e` on a recognized runner) — stream-redirection suppression (`2>/dev/null`) was
  deliberately removed as a category error, since redirecting stderr never alters `$?`. It also
  requires the masking runner be the LEADING command of a statement, and requires the mask to be
  in the SAME statement; a bare `<tool> test/check` fallback for an unrecognized launcher stays
  DEFERRED (`makoto/checks/verifierExitMasking.py:1-24`).
- `content.verifier_body_hollowed` targets the constitution integrity-check surface only
  (`constitution/integrity/checks/*.py`) and only two shapes — a hollow body (`return True` /
  `pass` / `assert True`) or a broad `except`/`except Exception`/`except BaseException` that
  swallows a failure into `pass`; a specific-typed except (e.g. `except ImportError`, an honest
  degrade-open) is excluded by design (`makoto/checks/verifierBodyHollowed.py:1-27`).
- `content.verifier_predicate_weakened` fires only on a narrow loose-comparator shape
  (`startswith(`/`endswith(`/`re.match`/`re.search`/`in [`) on the same constitution-checks path;
  it is a regex-file predicate, not a semantic check of what the comparator actually verifies
  (`makoto/checks/verifierPredicateWeakened.py:1-20`).

### Claim-completion / running-shipped claims (`gate.completion`, `gate.claimed_running`, `gate.claimed_shipped`, `gate.run_promised`/`content.run_intent_unfulfilled`, `content.false_green_claim`, `content.hollow_test`, `content.fabricated_tool_action`)

- `gate.claimed_running` reads only this session's own recorded Bash evidence, never the live
  world (Makoto "cannot itself go curl a port"); a liveness confirmation established another way
  (screenshot, browser devtools read) is invisible to it, a backgrounded launch (`cmd &`) that
  exits 0 at the shell level is treated as fail-open silence rather than proof of liveness, and
  evidence more than the 1-hour rolling window old reads as no-evidence even if the process is
  still running (`makoto/checks/claimedRunningAbsent.py:12-56`).
- `content.run_intent_unfulfilled` (`gate.run_promised`) checks only whether ANY Bash call
  followed a run-intent promise in the immediately next turn — never whether that call actually
  matches the promised action — and only the immediately prior turn's promise is ever checked; an
  older, already-unchecked promise is not re-litigated (`makoto/checks/runIntentUnfulfilled.py:9-55`).
- `content.false_green_claim` fires only on an exact expected-fail-count pattern; a genuinely
  clean run, or a run whose fail-count string doesn't match the recognized shape, does not fire
  (`makoto/checks/falseGreenClaim.py:20-23`).
- All claim-vs-evidence gates in this family are bounded by the same 1-hour `_select_recent`
  rolling window and by whichever agent-thread history `_history_for_agent` scopes them to
  (`makoto/_dispatch.py` ~207-243) — evidence outside that window or thread is invisible, not
  reasoned about as absent-with-confidence.

### Canon / citation (`gate.canon`, `gate.canon_fingerprints`, `gate.canon_fingerprints_advisory`, `content.phantom_citation`, `content.unsourced_webfetch`, `content.fabricated_commit_sha`)

- `content.phantom_citation` only enforces the canonical-citations allowlist for writes inside
  the tree that owns `CITATIONS.md`; if that governed root is unknown (no config row), it falls
  through to prior global behavior rather than silently disabling the check
  (`makoto/checks/phantomCitation.py:19-30`). It also fails open if the DB connection is `None`
  — "a missing DB must not block agent work" (`makoto/checks/phantomCitation.py:1-8`).
- `content.unsourced_webfetch` allowlists a fixed set of well-known documentation/reference hosts
  (`docs.anthropic.com`, `github.com`, `stackoverflow.com`, `wikipedia.org`, etc.) — a fabricated
  URL on one of those hosts is not distinguishable from a legitimate one by this check
  (`makoto/checks/unsourcedWebfetch.py:1-30`).
- `content.fabricated_commit_sha` requires an explicit positive commit/tag-happened assertion
  bound to a SHA-shaped token, and structurally excludes denials, deferrals, and references to a
  user-supplied SHA; a fabricated SHA presented without that assertion shape is out of scope
  (`makoto/checks/fabricatedCommitSha.py:1-30`).
- `gate.canon_fingerprints_advisory` covers 13 of the original 27 canon fingerprints at ADVISORY
  tier only — each rests on a soft/claim atom, or is among the atoms explicitly disqualified by
  the gold-oracle finding doc's robust core, and therefore never blocks
  (`makoto/checks/canonFingerprintsAdvisory.py:1-6`).

### Plan-drift / commitments (`gate.dropped`/`content.silently_dropped_commitment`, `gate.advance`/`content.undischarged_commitment`, `gate.plan_item_drift`, `content.deferred_checkbox_theater`, `gate.contract_order`, `content.stale_establisher`)

- `gate.plan_item_drift` is ADVISORY only, never blocking — a section/task-label commitment
  ("§9.3", "Task #19") has no filesystem ground truth to verify discharge against, so its
  "still open" signal is textual-only with no corpus-measured FP rate, unlike `gate.advance`'s
  verifiable file-vs-filesystem contradiction (`makoto/checks/planItemDrift.py:1-13`).
- `content.undischarged_commitment`'s rename-relocation tolerance recognizes only a same-parent,
  same-extension, version/variant-suffix rename (`parser.py` → `parser_v2.py`); an unrelated
  helper file touch (`auth.py` vs. `auth_helper.py`) does not discharge the commitment and the
  gate still fires — the boundary is deliberately narrow to avoid loosening a genuinely-dropped
  commitment into a false discharge (`makoto/checks/undischargedCommitment.py:23-33`).
- Every commitment/plan gate in this family shares the same 1-hour rolling-window bound as the
  claim-completion family above; a commitment sourced or discharged outside that window is
  invisible to the check that would otherwise catch it.

### Env-gated audit / integrity-suppression (`content.env_gated_audit`, `content.integrity_suppression_flag`)

- `content.env_gated_audit` (ACKNOWLEDGED FN, precision-first): an env-gated audit whose only
  audit operation sits in the `else` branch, or whose integrity intent is hidden behind a fully
  generic name in both the env-var key and the guarded body, evades detection. Kept precision-first
  because for a BLOCKING gate a false positive (blocking honest code) is the binding harm
  (`makoto/checks/envGatedAudit.py:31-34`).
- `content.integrity_suppression_flag` (ACKNOWLEDGED FN, cert §1.4): a deliberately-misnamed
  integrity suppression flag (e.g. `cache_skip = true` where "cache" is really the audit cache)
  evades — the threat model is honest-but-sloppy, not adversarial-deceptive-naming, and the prior
  pattern was equally evadable by the same rename (`makoto/checks/integritySuppressionFlag.py:23-27`).
  It also targets `.toml` only — `.md` was dropped because every corpus false positive there was
  a doc quoting an example, never live config (`makoto/checks/integritySuppressionFlag.py:8-14`).

## Required host/operator boundary

Makoto's `PreToolUse` decision is a policy signal at the moment the event is inspected, not a
containment mechanism at the moment a write actually lands, and its `Stop`-edge gates reason only
over what this session itself has ingested within a bounded window. As with Ward, the process
that actually performs a write, or the kernel policy applied to it, is the layer responsible for
containment — Makoto's denial is an early signal, not proof of where an allowed action's effects
will land or what the live world outside this session's recorded history currently looks like.

## Sources

- `makoto/_dispatch.py:104-321` — `_dispatch_fact`, `_self_verify_chain`, `_gates_enabled`,
  `_select_recent`, `main()`'s HYBRID fail-mode docstring.
- `makoto/substrate/_loader.py:1-22` — the loader's own discovery contract.
- Each cited `makoto/checks/*.py` module's own docstring, quoted above with file:line citations.
- `docs/ward-comparison.md` — the evidence review that identified these citations and this file's
  scope (item 1 of the "reintegrating Ward's model" list).
- `docs/CHECKS.md` — the generated id/edge/posture/description index (`tools/generate_checks_table.py`).
