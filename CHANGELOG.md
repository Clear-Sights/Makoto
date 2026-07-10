# Changelog

All notable changes to makoto. Versions follow the live check inventory
(`load_prechecks` / `load_stopchecks`), which the README count is tested against.

## [Unreleased]

### Changed
- **`stopchecks/` compat shim removed entirely.** `load_stopchecks()` relocated to its real,
  permanent home in `substrate/_loader.py` (alongside `load_checks`); its 11 callers
  (`_dispatch.py` + 10 test files) now import `GateContext`/`StopCheck`/`load_stopchecks` from
  their real locations instead of the deleted `makoto.stopchecks` package.
  `tests/test_stopcheck_self_wired.py` renamed to `test_self_wired_check.py`. Ported from
  makoto-dev via `tools/restructure_public.py`, not hand-patched. Note: this repo's
  `_dispatch.py` already runs its Stop-finding loop on `load_checks(edge="Stop")` (SPEC-C item 2),
  so `load_stopchecks()`/the `GATE = StopCheck(...)` exports are vestigial in production here,
  kept only for the tests that still assert against them directly — see the note in
  `substrate/_loader.py`'s `load_stopchecks` docstring.

## [2.0.0] — 2026-07-08

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
- **A runnable demo** (`docs/demo/render_demo.py` + `render_svg.py`): 3 real scenarios driven
  through the actual dispatchers (a genuine block, the full receipt story, a ConfigChange
  advisory fire), rendered to committed SVG "screenshots" via a small stdlib-only text-to-SVG
  renderer (no terminal-recorder dependency).

### Fixed
- `event.forbidden_location` now carves out the harness's own plan directory
  (`~/.claude/plans`), so writing a Plan file no longer root-escapes.
- `canon.timeout`'s retry hint no longer promises a discharge ("state explicitly why the error
  is acceptable") the detector cannot honor; the real discharge (a later successful call, or
  `release.operator`) is what it now says.
- `README.md` / `docs/MAKOTO-CONVENTIONS.md` count and mechanism claims re-audited against the
  live catalog; stale `skill-labV2` URLs updated to the project's current home.

## [1.4.0] — 2026-06-12

### Changed
- **License is now Apache-2.0** (was MIT): canonical `LICENSE` added; `plugin.json` updated.
- **Check tiers collapsed from four to two (Pre + Stop).** The taxonomy is by trigger event, so the
  one-member close-check tier (fired on Stop) and the empty post-check tier (would fire on
  PostToolUse, never populated) were folded away. `closecheck.liveness` is now the `gate.liveness`
  Stop gate (`stopchecks/stopcheck_liveness.py`; its analyzer engine + FP harness moved to
  `stopchecks/`); the `closechecks/` and `postchecks/` packages and their loaders are deleted. No
  behavior change — liveness still blocks live on illusory code; its falsify exemption (the analyzer
  is audited behaviorally, not by single-fn mutation) is now explicit in `falsify._BEHAVIORAL_TEETH`
  rather than implicit in the package boundary. New inventory: **18 pre-checks, 8 Stop gates**.

### Added
- **Exemption audit (`exemptions.jsonl`)** — the `makoto-allow` escape valve now leaves an
  on-the-record trace. Content-scan factories DETECT first and, when a marker suppresses a
  CONFIRMED match, the dispatcher records {pattern, file, line, reason, session, tool} via an
  injected sink (`lib.factories.set_exemption_sink`, filled by `_dispatch`; L1 stays L0-pure;
  pure unit calls unchanged). `MAKOTO_DISABLE_PATTERNS` muting a keyword-hit pattern records a
  `disabled-pattern` row too — parity with the already-audited gate switch. New
  `audit.append_exemption` / `audit.read_exemptions` (shared `_read_jsonl` with `read_rows`);
  9 behavioral pins in `tests/test_exemption_audit.py`. No new gate: check inventory unchanged
  (18 pre-checks, 8 Stop gates); a suppressed fire still never blocks — it is just no
  longer silent.

## [1.3.1] — 2026-06-10

### Fixed
- **`makoto install` double-dispatch on a hand-wired device** — `_wire_claude_hooks` keyed its
  idempotency on the `_makoto_managed` flag, so a flag-less shim entry (command →
  `makoto_state/dispatch.sh`, the same install state v1.2.1 taught `_hooks_wired` to recognize)
  survived the strip and the installer appended a duplicate: two dispatch fires per event. The
  functional wiring truth now lives in one shared helper (`_entry_dispatches_to_makoto`) used by
  both the wirer and status; install absorbs any entry already dispatching to makoto into the
  single managed entry. Caught live on the first 1.3.0 device update; no gate/inventory change —
  the live catalog is unchanged at 18 pre-checks / 1 close-check / 7 Stop gates.

## [1.3.0] — 2026-06-10

### Added
- **3-line conventions block + just-in-time delivery** — `makoto install` now writes only the law
  into `CLAUDE.md` (the monotonicity invariant as falsifiability-preservation, the `makoto-allow`
  convention, a pointer to `docs/MAKOTO-CONVENTIONS.md`), returning ~40 lines to the contract's
  adherence budget. The flagged-shapes catalog arrives at fire time instead: every block decision's
  `retry_hint` carries the check's convention, the escape hatch (iff that check honors the marker —
  a source-bound 14-of-18 set; event-shapes `1.9`/`1.21`/`1.22`, the `1.23` self-mute, and `gate.*`
  never get one), and the conventions pointer. Guidance lands adjacent to the decision it binds and
  costs zero context when nothing fires.
- **`gate.stale_pass`** — the 7th end-of-turn gate: a whole-suite pass-claim ("all tests pass")
  contradicted by pytest's own `lastfailed` record naming a node that still exists and was last
  observed failing. Evidence is a direct-pointer read of `<cwd>/.pytest_cache/v/cache/lastfailed`
  (`lib/pytest_cache.py`), existence-filtered so deleted/renamed entries don't fire (a `def <name>`
  presence check killed all 42 stale entries on this repo's green suite with 0 false survivors).
  Post-check-class latency contract: 50-entry / 256KB caps, no directory enumeration of any kind
  (measured 4.9ms real-repo, 0.01ms no-claim, 10× headroom).
- **`postchecks/` — the 4th check tier.** A `PostToolUse` category (folder + `load_postchecks` loader
  + dispatch wiring) for result-vs-record contradictions resolvable by a direct pointer, budgeted
  `pre < close < post << stop` at ~200-300ms. Wiring is live; the catalog is deliberately empty,
  awaiting patterns that graduate into it.
- **`audit_hookup` artifact-orphan enforcement** — every state-artifact glob must have a writer and
  every committed `data/` file a reader, so a dead read can't outlive its producer (proven by
  temporarily re-adding the cut `chain_*.log` glob → flagged `('unwritten-read', …, install.py:200)`).
- **`scripts/expected_fires.json`** — pins pre-check `1.34`'s 402 cross-project true-positive fires
  per session (9 historical sessions whose commits genuinely embed an AI-authorship trailer);
  `measure_corpus_fp` reconciles strict both ways — a new or risen fire is a regression, a vanished
  pinned fire means the detector weakened, an absent file fails closed.
- **Connectivity coverage** — all 7 Stop gates now probed hermetically (each on a fresh `mkdtemp`
  pytest-cache, never the repo's) with a completeness guard deriving probed-vs-`load_stopchecks()`
  and exiting non-zero on any unprobed or extra gate, so an 8th gate cannot silently skip the probe;
  plus a `1.34` spec and the `1.6` governed-tree probe fix (the probe wrote outside the seeded tree,
  so the correct `_within_governed_tree` guard suppressed the fire — `_build_specs` now writes under
  the seeded root). `check_all` is 10/10 green.

### Changed
- **The I/O purge** — a verdict-ledger pass that cut or absorbed dead I/O across the tree: the
  research/mining tier (`miner/`, `redteam_mine`, `predict_check`, `audit_ratchet`) and the dark
  gates were removed; `recheck_survivors` folded into `audit_lines --recheck`, `runtime_manifest.py`
  into its `.toml` marker, `redteam_seed` into `redteam_score`. Every cut's design + numbers are
  preserved no-loss in `docs/MAKOTO-BIBLE.md` (the new master reference) and the decision trail in
  `docs/superpowers/2026-06-09-io-verdict-ledger.md`. The test count went from 1148 to 1092 with
  the affected tests redistributed, not dropped.
- **`iter_tool_events` → `lib/io`** — relocated verbatim; `precheck_1_22`'s commit-history reader
  converges onto the shared definition.

### Fixed
- **`gate.dropped` `_EMPTY_OK` discharge** — the `named_artifact` and `line_range` arms now honor
  conventional empties (an empty `__init__.py` Write *is* the deliverable), mirroring
  `_common._discharged`; previously the gate false-fired on honest empty files.
- **`audit_orthogonality._RELEVANT_TESTS`** — dropped the stale references to `test_gate_meaning.py`
  and `test_hidden_retraction_gate.py` (deleted with the dark gates); their stale refs broke
  `--module` runs.
- **`db.py` `commitments` table** — removed the never-written `source_event_id` column (the
  `INSERT` names its columns explicitly without it, and every `SELECT` is named), with all 11 mirror
  DDL strings updated to match.

## [1.2.1] — 2026-06-08

### Fixed
- **`makoto status` `hooks_wired`** — the check keyed on the `_makoto_managed` marker (which exists for
  idempotent uninstall), so a hand-wired / shim install (command → `makoto_state/dispatch.sh`, no flag)
  reported `hooks_wired: false` on a device where makoto was in fact firing. Now detects the functional
  truth: a hook entry is wired if it carries the managed flag OR any inner command dispatches to makoto.
  No gate/inventory change — the live catalog is unchanged at 18 pre-checks / 1 close-check / 6 gates.

## [1.2.0] — 2026-06-07

### Added
- **`gate.named_test`** — the 6th end-of-turn gate: a named-test pass-claim ("`test_foo` passes")
  contradicted by a recorded, unresolved `FAILED` of that exact test. Coreference-pinned
  (`test_foo` ≠ `test_foobar`); the orthogonal delta to `gate.green_claim`'s whole-suite firewall.
  Per-test FAILED evidence, per-test PASS discharge, stateless over `ctx.history` (ANSI-stripped).
  FP=0 over the 1441-session corpus; 20 sentinels green.

### Fixed
- **`gate.green_claim` ANSI resolver** — vitest/jest colorize their summary (`\x1b[31m2 failed`); the
  SGR terminator `m` is a word char abutting the digit, which killed the `\b` before `[1-9]\d* failed`
  and let colorized failures read as silent. `is_failing_testrun` now strips ANSI first. Proven
  FP-safe: 0 testrun outputs flip non-failing→failing across the 1441-session corpus.

### Docs
- README corrected to the live inventory (18 pre-checks, 1 close-check, 6 end-of-turn gates) and now
  lists `gate.fabricated_action`, `gate.named_test`, and the `closecheck.liveness` family that prior
  versions omitted. A new materiality test binds the README's stated counts to the live loaders so the
  doc cannot silently go stale again (makoto's own falsifiability, applied to its README).

## [1.1.0] — 2026-06-06

### Changed
- Taxonomy rename: `Pattern`→`PreCheck` (`predicates/`→`prechecks/`), `Gate`→`StopCheck`
  (`gates/`→`stopchecks/`), and a new `CloseCheck` category (`closechecks/`) with its own loader.
- Added `closecheck.liveness` — function-internal dead/illusory-statement detection on closed units.
- Added pre-check `1.34` — an illusory AI-authorship commit trailer the agent never wrote.
