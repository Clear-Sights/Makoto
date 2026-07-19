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

**If you write a flagged shape legitimately, annotate it with `makoto-allow: <reason>`** on or
near that line (any comment style; case-insensitive; the reason must be non-empty). Makoto then
will NOT flag it. Use it honestly — the marker is an on-the-record, auditable rationale, not a
way to disguise a real integrity violation.

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
- `content.deferred_checkbox_theater` — DEFERRED checkbox theater on an open T-item
- `content.phantom_citation` — a phantom citation: an Author-Year cite not in the project's canonical `CITATIONS.md` (also exemptable via the catalog's citations allowlist)
- `content.verifier_body_hollowed` — a verifier neutered: body hollowed (`return True` / `pass` / `assert True`) or a broad `except` swallowing the failure, on the integrity-check surface
- `content.illusory_authorship_trailer` — an illusory AI-authorship trailer in a commit command or written content (the agent claiming an authorship identity it does not hold)

Event shapes — `makoto-allow` does NOT apply (the evidence is the event itself, not file content):

- `content.unsourced_webfetch` — a WebFetch URL never seen in any prior tool result this session
- `content.verifier_exit_masking` — verifier exit-code masking (`|| true` / `; true` / `set +e` on a test/build/lint runner)
- `content.fabricated_commit_sha` — a fabricated commit SHA/tag presented as proof of a commit no `git commit`/`tag` produced
- `content.self_mute_guard` — makoto self-mute: disabling/un-wiring makoto via `settings.json`. Never exemptable, in-band or out: the seal on the mint cannot be signed by the would-be forger.
- `event.thrash_revert` — a whole-file `Write` reverts a file back to an earlier byte-identical whole-file content after an intervening different-content `Write` to the same path (an A->B->A self-revert with no net progress); no `makoto-allow` escape hatch is implemented for it.
- `event.identical_retry`: a byte-identical Bash retry immediately following that SAME call's DETERMINISTIC failure (a syntax/import/permission/not-found error), with no intervening state change. The proactive twin of `canon.recur`: kills a stuck retry loop at length 1, before the redundant call even runs. Never fires on a transient failure (timeout, connection-refused, 5xx/429) or an ambiguous one: `checks/_failureClassifier.py`'s own fail-toward-uncertain contract.
- `gate.contract_order` — a result-producing tool call issued while a declared Plan's dependency for that step is still undischarged (SPEC-5, ported by shape from Assay's `ContractOrder`); its Stop-time sibling gate of the same id guards the remainder at turn end. The evidence is the plan store's own recorded order, not file content.

End-of-turn gates (`gate.*`) check your closing **claims against the recorded ledger** — they
have no content line to annotate, so `makoto-allow` does not apply; the discharge is doing (or
honestly retracting) the thing you said.

This file is the pointer target of the makoto-managed `CLAUDE.md` block; refresh it with
`makoto install`, remove the block with `makoto uninstall`.
