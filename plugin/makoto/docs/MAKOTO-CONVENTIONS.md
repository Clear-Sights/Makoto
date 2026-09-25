# Makoto conventions

Makoto is an AI-integrity hook (it watches *your* tool calls, never the user's). It flags
content shapes that commonly indicate **weakening an integrity / audit / verification check**.

Your `CLAUDE.md` carries only the three-line law (the monotonicity invariant, the
`makoto-allow` convention, and a pointer here). Everything below is delivered
**just-in-time**: when a check fires, its block message carries that check's convention and —
where it applies — the `makoto-allow` escape hatch. Guidance lands at the moment it binds and
costs zero context when it doesn't.

## The monotonicity invariant — falsifiability-preservation

A word's meaning may only be **preserved or deepened — never degraded, skipped, or bypassed.**
Monotonicity *is* falsifiability-preservation: a word's meaning may never become **less
checkable**. When you say "test X," X carries a definition; from that moment X may become *more*
complete or *more* meaningful, never less. Loosening a verifier, gating a check behind an env
var, deleting an assertion, or routing around the hook all make a once-real word empty.
**A bypassable test was never a test.** This is why muting makoto is not an in-band,
self-annotated decision: the seal on the mint cannot be signed by the would-be forger
(disable out-of-band, or run `makoto uninstall`).

## The `makoto-allow` convention

Where a finding's retry hint offers `makoto-allow: <reason>`, place the marker as directed
with a non-empty rationale. The check owns its accepted location and exemption scope.

```toml
cache_skip = true  # makoto-allow: disables a perf cache for this dev profile — not an integrity check
```

```python
if os.environ.get("ENABLE_AUDIT_TRAIL"):  # makoto-allow: app feature, gates user-facing audit logging
    write_audit_trail()
```

## The flagged shapes (the live catalog; each delivers its convention when it fires)

Content shapes — `makoto-allow: <reason>` exempts a legitimate instance:

- `content.verifier_predicate_weakened` — verifier predicate weakened: a loose comparator (`startswith` / `endswith` / `re.match` / `in [...]`) in an integrity-check file
- `content.env_gated_audit` — audit/verification code gated behind an env var (`if os.environ.get(...)` / `os.getenv(...)` gating an integrity op)
- `content.integrity_suppression_flag` — an integrity-named suppression flag (`*_skip` / `*_bypass` / `*_inapplicable = true`) in a `.toml` with no ADR backlink
- `content.phantom_citation` — a phantom citation: an Author-Year cite not in the project's canonical `CITATIONS.md` (also exemptable via the catalog's citations allowlist)
- `content.verifier_body_hollowed` — a verifier neutered: body hollowed (`return True` / `pass` / `assert True`) or a broad `except` swallowing the failure, on the integrity-check surface
- `content.illusory_authorship_trailer` — an illusory Claude/Anthropic authorship or generation attribution (the literal trailer form, a `Claude-Session:` link, the routing address, or "Generated with/by Claude") in a commit command, written content, or a GitHub MCP body <!-- makoto-allow: documenting the policy verbatim, not adding the trailer --> (a plain "Claude Code" product-name mention is not matched)
- `gate.claude_identity` — a `git commit`/`merge`/`pull`/`cherry-pick`/`revert`/`am`/`rebase` whose author or committer resolves to Claude from the git layer (env var or config file, named in the refusal), or a `git push` whose outgoing commits carry one
- `content.illusory_interruption_claim` — a fabricated "interrupted by user" claim in a commit command or written content, with no genuine harness-set interruption anywhere in this session's recorded history
- `content.last_wins` — a dict literal or JSON object repeats a key with a different value, so the last one silently wins. Give each key one value.
- `content.bound_as_count` — a test asserts `len(...)` or `.count(...)` under a literal ceiling (`<`, `<=`); assert the exact count the fixture produces.

Event shapes — `makoto-allow` does NOT apply (the evidence is the event itself, not file content):

- `content.unsourced_webfetch` — a WebFetch URL never seen in any prior tool result this session
- `content.verifier_exit_masking` — verifier exit-code masking (`|| true` / `; true` / `set +e` on a test/build/lint runner)
- `content.fabricated_commit_sha` — a fabricated commit SHA/tag presented as proof of a commit no `git commit`/`tag` produced
- `content.self_mute_guard` — makoto self-mute: disabling/un-wiring makoto via `settings.json`. Never exemptable, in-band or out: the seal on the mint cannot be signed by the would-be forger.
- `event.nested_budget` — a `timeout N` inside a Bash call whose own limit is shorter, so the inner budget is never reached; no `makoto-allow` escape hatch is implemented for it.
- `event.thrash_revert` — a whole-file `Write` reverts a file back to an earlier byte-identical whole-file content after an intervening different-content `Write` to the same path (an A->B->A self-revert with no net progress); no `makoto-allow` escape hatch is implemented for it.
- `event.identical_retry`: a byte-identical Bash retry immediately following that SAME call's DETERMINISTIC failure (a syntax/import/permission/not-found error), with no intervening state change. The proactive twin of `canon.recur` (the stuck-retry canon fingerprint): kills a stuck retry loop at length 1, before the redundant call even runs. Never fires on a transient failure (timeout, connection-refused, 5xx/429) or an ambiguous one: `kit.classify_failure`'s own fail-toward-uncertain contract.
- `event.unbriefed_dispatch` — an Agent/Task dispatch prompt carries no line-start `READ:`, `WRITE:` and `ACCEPTANCE:` line; opt-in only (`makoto.toml` `dispatch = true`), no `makoto-allow` escape hatch.
- `event.unpinned_input` — a dispatch `READ:` path names no `@<12+ hex>` content pin, or a long-timeout (`> 120000` ms) Bash call names no pin and verifies none (`sha256sum -c`); opt-in only (`makoto.toml` `dispatch = true`), no `makoto-allow` escape hatch.
- `gate.unknown_ref_switch` — a `git checkout`/`switch`/`reset --hard <ref>` with no `git branch`/`rev-parse`/`show-ref` earlier in the session; print the refs, then retry.
- `gate.unprobed_fanout` — a subagent dispatch with no Read, Glob or Grep earlier in the session; read the ground, then retry.
- `gate.relaunched_unchanged` — a second worker launch with no verifier run anywhere before it; run the target's probe, then retry.
- `gate.unobserved_destruction` — a destructive command (`rm -rf`, `git reset --hard`, `git clean -f`, force push, ...) with no verifier run earlier in the session; run the relevant test or probe, then retry.
- `gate.report_before_run` — a Write/Edit putting a run verdict ("all tests pass", `58 passed`) into a prose file before any verifier ran; run it, then write what it printed.
- `gate.unasked_plan` — `ExitPlanMode` with no `AskUserQuestion` earlier in the session; ask one question, then present the plan.
- `gate.undischarged_waiver` — a Write/Edit introducing a checker-silencing directive (`noqa`, `type: ignore`, `eslint-disable`, a bare skip, ...) with no checkable end on or above it; name the end (a tracked item, a date, `until ...`) or fix the finding.
- `gate.plan_item_drift` (end of turn, blocking) reads the plan-item store, not a declared Plan: an open PLAN/TASK-labeled promise sourced from chat prose (`state.plan.source_plan_item_promise`) or from the harness's own `TaskCreate`/`TaskUpdate` calls, recorded via `state.plan.record_plan_item`/`record_task_event` and read back un-windowed by session with `open_plan_items`. Nothing declares a Plan file today; the old JSONL-node mechanism (`gate.stale_establisher`, `gate.contract_order`) was cut 2026-09-24.

End-of-turn gates (`gate.*`) check your closing **claims against the recorded ledger** — they
have no content line to annotate, so `makoto-allow` does not apply; the discharge is doing (or
honestly retracting) the thing you said.

This file is the pointer target of the makoto-managed `CLAUDE.md` block; refresh it with
`makoto install`, remove the block with `makoto uninstall`.
