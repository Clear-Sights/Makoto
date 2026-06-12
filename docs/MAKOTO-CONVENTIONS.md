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

- `1.1` — verifier predicate weakened: a loose comparator (`startswith` / `endswith` / `re.match` / `in [...]`) in an integrity-check file
- `1.2` — audit/verification code gated behind an env var (`if os.environ.get(...)` / `os.getenv(...)` gating an integrity op)
- `1.4` — an integrity-named suppression flag (`*_skip` / `*_bypass` / `*_inapplicable = true`) in a `.toml` with no ADR backlink
- `1.5` — DEFERRED checkbox theater on an open T-item
- `1.6` — a phantom citation: an Author-Year cite not in the project's canonical `CITATIONS.md` (also exemptable via the catalog's citations allowlist)
- `1.26` — TLS/certificate verification disabled (`verify=False` / an unverified SSL context)
- `1.27` — a verifier neutered: body hollowed (`return True` / `pass` / `assert True`) or a broad `except` swallowing the failure, on the integrity-check surface
- `1.28` — JWT signature verification disabled (`jwt.decode` with `verify=False` / `verify_signature: False`)
- `1.29` — certificate verification disabled (`SSLContext.verify_mode = CERT_NONE`)
- `1.30` — a timing-unsafe `==`/`!=` comparison of a secret/HMAC/digest (use `hmac.compare_digest`)
- `1.31` — a JWT decode allow-list whitelisting the unsigned `none` algorithm (alg-confusion bypass)
- `1.32` — paramiko SSH host-key verification weakened to `AutoAddPolicy`/`WarningPolicy`
- `1.33` — `cert_reqs=ssl.CERT_NONE` disabling peer-certificate verification at the call site
- `1.34` — an illusory AI-authorship trailer in a commit command or written content (the agent claiming an authorship identity it does not hold)

Event shapes — `makoto-allow` does NOT apply (the evidence is the event itself, not file content):

- `1.9` — a WebFetch URL never seen in any prior tool result this session
- `1.21` — verifier exit-code masking (`|| true` / `; true` / `set +e` on a test/build/lint runner)
- `1.22` — a fabricated commit SHA/tag presented as proof of a commit no `git commit`/`tag` produced
- `1.23` — makoto self-mute: disabling/un-wiring makoto via `settings.json`. Never exemptable, in-band or out: the seal on the mint cannot be signed by the would-be forger.

End-of-turn gates (`gate.*`) check your closing **claims against the recorded ledger** — they
have no content line to annotate, so `makoto-allow` does not apply; the discharge is doing (or
honestly retracting) the thing you said.

This file is the pointer target of the makoto-managed `CLAUDE.md` block; refresh it with
`makoto install`, remove the block with `makoto uninstall`.
