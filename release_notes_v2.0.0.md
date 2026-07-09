### Changed (breaking)
- **The append-only store is now a tamper-evident hash chain, not mutable SQLite.** `ledger.py`
  absorbs a hash-chained JSONL store (`row_hash = norm_sha256(prev_hash + canonical(row))`,
  exclusive `flock` across read-then-write, proven under concurrent thread/process races);
  `_dispatch.py` self-verifies the chain at every hook event; every audit row is now
  chain-appended too, so the audit trail and the tamper-evident record are the same object.
  sqlite remains a derived, disposable query index.
- **One registration, one namespace.** The dual catalog (`patterns.toml` + `predicate_module` +
  separate `load_prechecks`/`load_stopchecks` loaders, plus the literal double
  `GATE = StopCheck(...)` / `CHECK = _Check(...)` registration at the bottom of every gate file)
  is unified: one `CHECK` export per file, discovered by a flat-folder scan
  (`checks/_loader.py`). `data/patterns.toml` is deleted, dead weight once the loader became the
  catalog. Every check id now follows one `family.name` scheme (`content.*` for text/AST
  judgments, `event.*` for tool-call-structure judgments, `gate.*` for end-of-turn ledger
  judgments); the 23 legacy numeric/dotted ids (`1.26`, `makoto.forbidden_location`,
  `write.thrash_revert`, …) remain permanent aliases (`checks/_aliases.py`), never dead.
  **New inventory: 22 pre-checks, 16 live Stop-tier checks** (14 blocking-capable gates, 12 of
  which actually block; `gate.self_wired`/`gate.canon_fingerprints_advisory` stay advisory by
  design, plus 2 permanently-advisory catalog-completeness checks, `gate.stale_establisher` and
  `gate.undeclared_falsifiable`, outside that 14-gate contract entirely).
- **One voice.** `retry_hint`/`description` for the Pre-tier moved out of inline `Check(...)`
  literals into module-level `RETRY_HINT`/`DESCRIPTION` constants, so a hint and its detector can
  never silently drift apart (`tests/test_check_voice.py`, AST-verified).
- **`ack-block` renamed to `release.operator`** (the discharge phrase for a permanently-fired
  session-level canon fingerprint). The legacy phrase (`makoto ack-block <id>: <reason>`) is
  honored forever; an id/phrase is never retired, only aliased.

### Added
- **The receipt: word, deed, record, receipt.** `receipt.py` + `makoto receipt [--session
  <id>]`: every clean turn's claims, each trace-bound to a `verify_chain`-checkable chain row,
  with an honest exemption count. Makoto now issues tender for the word it keeps, not only a
  block for the one it doesn't.
- **`gate.canon` / `gate.canon_fingerprints`**: two language-agnostic Stop primitives
  (`canon.timeout`, `canon.recur`) plus 4 of 17 ported session-level "canon" fingerprints
  (`gate.canon_fingerprints`, blocking, 0-FP-certified) and the other 13
  (`gate.canon_fingerprints_advisory`): session-level gaming-shaped detection over the turn's
  own recorded call stream, independent of language or test-runner regex.
- **ConfigChange watch** (`_dispatch_configchange.py`, optional, wired separately from the
  Pre/Post/Stop hooks): advisory-only detection of makoto's own hooks being stripped from
  `.claude/settings.json`, plus an evidence-gated **blocking** tier (`gate.configchange_transition`)
  that fires only on a genuinely evidenced had-hooks-then-stripped transition (an install
  manifest hit, or a prior same-path observation). A path with no such evidence never blocks,
  no matter how many times it evaluates as stripped.
- **`event.identical_retry`**: the proactive twin of `canon.recur`. A byte-identical failing
  Bash retry with no intervening state change is redirected before the redundant call even runs,
  gated on `checks/_failureClassifier.py`'s deterministic-vs-transient discrimination (never
  fires on a legitimate timeout/5xx/429 re-poll).

### Fixed
- `event.forbidden_location` now carves out the harness's own plan directory
  (`~/.claude/plans`), so writing a Plan file no longer root-escapes.
- `canon.timeout`'s retry hint no longer promises a discharge ("state explicitly why the error
  is acceptable") the detector cannot honor; the real discharge (a later successful call, or
  `release.operator`) is what it now says.
- `README.md` / `docs/MAKOTO-CONVENTIONS.md` count and mechanism claims re-audited against the
  live catalog; stale `skill-labV2` URLs updated to the project's current home.
