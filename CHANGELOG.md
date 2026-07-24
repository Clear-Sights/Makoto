# Changelog

All notable changes to makoto. Versions follow the live check inventory
(`load_prechecks` / `load_checks(edge="Stop")`), which the README count is tested against.

## [Unreleased]

### Added
- **`gate.claimed_running`** — a new blocking end-of-turn gate: the assistant claims an ongoing
  process/service liveness state ("the server is running", "it's up and listening on port 5173")
  that this session's own recorded Bash evidence contradicts — either no process-start or
  liveness-check command ran at all this session, or the most recently recorded one ended in a
  direct error state (interrupted, or a non-zero exit code). The claim signal requires a
  co-occurring first-person process-start verb ("I started / launched / ran ...") in the same
  message, so generic explanatory prose about a tool's default behavior doesn't trip it. 15th
  end-of-turn gate; see `makoto/checks/claimedRunningAbsent.py`.
- **`gate.run_promised`** — a new blocking end-of-turn gate, the forward-looking sibling of
  `gate.claimed_running`: the immediately prior turn made a first-person run-intent promise
  ("I'll run the tests", "let me deploy this") with no Bash call anywhere in the session's
  recorded history since. One-turn grace period: a promise made this turn can only be checked
  starting at the next one. 16th end-of-turn gate; see `makoto/checks/runIntentUnfulfilled.py`.
- **`gate.claimed_shipped`** — a new blocking end-of-turn gate, sibling to `gate.claimed_running`/
  `gate.run_promised`: the assistant claims a REMOTE mutation is already done ("I merged the PR",
  "pushed it to main", "it's live now") but no successful remote-mutating tool call appears
  anywhere in the session's recorded history. Evidence is a non-dry-run `git push` over Bash, or
  a successful call from a closed GitHub MCP tool set (`merge_pull_request` — requiring `merged:
  true`, not just an error-free response — and `push_files`); `create_pull_request` is
  deliberately excluded, since opening a PR establishes intent but does not substantiate "merged"
  or "live". Reads pooled cross-agent history so a subagent's real push/merge grounds a
  main-thread claim, same reasoning as `gate.claimed_running`. Immediate check, no grace period.
  `gate.completion` keeps sole ownership of local file-production claims. 17th end-of-turn gate;
  see `makoto/checks/claimedShippedAbsent.py`.

### Fixed
- **`_DESTRUCTIVE_RX`/`_DISABLE_RX` no longer false-block a safe `git push --force-with-lease` or
  `--force-if-includes`.** Both regexes' bare-force checks matched `--force\b` — a word boundary
  fires right after "force" regardless of what follows, so a hyphen (a non-word character) let
  these safe flags match identically to a bare `--force`, even though both are git's own SAFE
  alternative (each refuses to push if the remote ref moved since the last fetch). Every
  bare-force alternative is now `--force\b(?!-)`, excluding both safe flags while leaving bare
  `--force`, `-f`, and every other destructive/disable clause unaffected.
- **`gate.completion` no longer false-blocks a true claim that refers to a well-known file by its
  bare, extensionless name** (e.g. "I updated the CHANGELOG" against a real `CHANGELOG.md` touch).
  `_suffix_match` required the final path component to match exactly, so a claim binding to bare
  "CHANGELOG" never matched a real touch at `.../CHANGELOG.md`. It now also accepts an
  extensionless short side against a long side whose final component is `<short>.<recognized
  extension>`; the existing firewall (`auth.py` never matches `auth_helper.py`) is unaffected.
- **`canon.destructive_command` no longer false-blocks a read-only `dd`, and now catches a
  force-push/hard-reset/interactive-clean wherever its trigger flag actually sits.** `dd if=`
  fired on any `dd` invocation regardless of whether it also wrote anywhere (`of=`) — using
  `dd` as a byte-range reader (piped to `fold`/`xxd`, no `of=`) tripped `destructive_command`
  for the rest of the session. Also generalized the same fix to the rest of the denylist:
  `git clean`/`git push`/`git reset --hard` required their trigger flag immediately after the
  base command, missing e.g. `git push origin main --force`; `git clean`/`git push` now also
  veto on a real `-n`/`--dry-run` found anywhere in the command; and `git checkout -- .` had a
  regex bug that made it dead code (it could never actually match). `mkfs.*`'s own `-n` was
  deliberately left alone — it means dry-run for `mkfs.ext4` but volume-label for `mkfs.vfat`,
  so a blanket exclusion would have silently created a false negative on a real format. (#10)
- **`canon.recur` no longer stays permanently stuck once a retry loop genuinely resolves.**
  Verdict is now judged per (tool, input) key, and the last judgment for each key wins: a later
  success for that key silences it even when different calls happened in between, while a
  genuinely still-stuck key still fires.

### Added
- **`content.illusory_authorship_trailer` widened** to also catch the routing address
  (`noreply@anthropic.com`), a `Claude-Session:` trailer, and "Generated with/by Claude"
  prose — not just the literal git trailer. A plain "Claude Code" product-name mention is
  deliberately not matched.
- **New `content.illusory_interruption_claim`**: catches a fabricated "interrupted by user"
  claim, grounded against this session's own recorded history.

### Fixed
- **`gate.completion` no longer false-blocks a true claim about a file landed via a local
  `git pull` from another machine.** A file produced on a remote machine over ssh and synced
  locally is on disk under that repo's root, not under `cwd`, so a bare-name claim
  (`"index.md"`) missed it. `makoto/checks/_worldpaths.py` widens the Stop-gate's
  `fs_exists`/`fs_size`/`fs_read` closures: on a cwd-relative miss, resolve against git
  work-trees this session actually synced (from the session's own Bash history), requiring
  the candidate be git-tracked and suffix-match the claim at a path-separator boundary. Every
  alternate path still ends in a live `os.path.exists`, so a claim about a file that exists
  nowhere still blocks — this widens observation, never the verdict. (#2)
- **8 hard-deny security checks (cert/JWT/SSH-host-key/timing-safe-compare/forbidden-location)
  removed** — moved to a new sibling project, [Clear-Sights/Ward](https://github.com/Clear-Sights/Ward),
  already re-implemented there with parity tests. `_ALLOW_EXEMPT_IDS`, `docs/MAKOTO-CONVENTIONS.md`,
  and the pre-check count (22 → 14, README/plugin.json/marketplace.json) now agree with the
  actually-shipped catalog.

## [2.1.1] — 2026-07-17

### Fixed
- **The dispatch shim can no longer be shadowed or silently die.** `_dispatch_shim.sh` ran
  `python3 -m makoto._dispatch` with no path setup, so resolution depended entirely on the
  hook process's working directory: any stray `makoto/` directory there shadowed the plugin
  package, and in the common case (no `makoto/` in cwd at all) EVERY hook died with
  `ModuleNotFoundError` exit 1 — a 100% failure rate on the marketplace install, observed
  live. The shim now cd-pins to `$CLAUDE_PLUGIN_ROOT` before exec, and an unset/unusable
  plugin root fails OPEN with a guaranteed-loud stderr line and an empty envelope, matching
  `_dispatch`'s own HYBRID fail-mode. Pinned by `tests/test_dispatch_shim.py`, which runs the
  shim against a bare venv interpreter so a dev editable install can't mask the regression.
- **`plugin.json` version no longer lags the release.** It still said 2.0.0 while
  `pyproject.toml` said 2.1.0, so the marketplace reported a stale version; both now carry
  the release version.

## [2.1.0] — 2026-07-12

### Fixed
- **SessionStart and SubagentStop now actually fire.** Both hook handlers had real,
  tested implementation code that never ran in the shipped plugin because
  `hooks/hooks.json` never wired either event -- graduated from dead code to wired,
  verified by a live-fire subprocess smoke test.
- **The README's "Live demo" section is now backed by real artifacts.** Its three
  embedded SVG screenshots and the `docs/demo/render_demo.py` / `render_svg.py` scripts
  it names were absent from the tree -- the landing page showed broken images. The demo
  is rebuilt for real: three scenarios driven through the actual dispatchers (a
  PreToolUse block, the full word->deed->record->receipt chain including the test-delta
  redirect, a ConfigChange advisory), genuine logged output under `docs/demo/logs/`,
  SVGs rendered from those logs, and the receipt scenario reproducing the README's
  promised numbers exactly. A new smoke test (`test_readme_references_exist`) fails CI
  on any README reference to a missing file.
- **README**: the revoked legacy `makoto ack-block` phrase is no longer documented
  (`release.operator` is the only discharge, per the epoch reset below), and the
  citations-seed path reflects the package layout (`makoto/docs/CITATIONS.md`).
- **`content.self_mute_guard` now catches a selective self-mute via
  `MAKOTO_DISABLE_PATTERNS`.** The guard's env-var regex was truthy-only (`1|true|yes|on`)
  -- right for the boolean-shaped `MAKOTO_DISABLE_GATES`/`MAKOTO_PAUSE`, but
  `MAKOTO_DISABLE_PATTERNS` takes a LIST of check ids, and a canonical-id list
  (`"content.self_mute_guard"`) starts with no truthy literal, so an in-session
  settings.json edit disabling specific checks -- including this guard itself -- passed
  unseen. Any non-empty, non-falsy value now fires; emptying the var (the re-enable
  move) stays silent.

### Changed
- **Legacy numeric ids scrubbed from every live surface** (post-epoch-reset sweep):
  check module docstrings self-identify by canonical id, cross-references between
  checks use canonical ids, README's CLI examples use canonical ids, and
  `content.phantom_citation`'s retry_hint names the real canonical-CITATIONS.md path
  instead of the deleted `data/patterns.toml` allowlist. Dated historical notes keep
  their period ids by design -- they are facts about that date.
- **Package moved from repo root into `makoto/`** (owner decision, 2026-07-10): the repo
  landing page now reads as a product -- README/LICENSE/CHANGELOG, `hooks/`, `commands/`,
  `docs/`, `tests/`, one `makoto/` package -- instead of the package's own underscore
  internals scattered at root. The package took its runtime data with it
  (`makoto/docs/CITATIONS.md`, `makoto/docs/MAKOTO-CONVENTIONS.md`) and the dispatch shim
  (`makoto/_dispatch_shim.sh`); every runtime path was already `__file__`-relative, so only
  `pyproject.toml`'s package-dir mapping and `hooks/hooks.json`'s shim path changed. Dotted
  module paths (`makoto._dispatch` etc.) are untouched -- existing installs keep working.

### Removed (epoch reset, owner decision 2026-07-10)
- **The legacy-id alias table and every dual-form acceptance are gone.**
  `substrate/_aliases.py`, the alias closure in `MAKOTO_DISABLE_PATTERNS`, the CLI's
  legacy-id resolution, the `makoto ack-block` discharge phrase, and the `ack-block`
  chain kind are all removed: `family.name` ids and `release.operator` are the only
  forms. Rationale: the sole justification for the aliases was keeping immutable
  historical state readable -- the owner retired that guarantee outright. Operators
  upgrading across this reset archive (zip) or wipe `$MAKOTO_STATE_DIR` and start a
  fresh epoch; records predating it cite retired names by design.

### Changed
- **Public scope narrowed to the consumed artifact** (owner decision, 2026-07-10): this repo
  now ships exactly what a plugin consumer uses (the runtime package, hooks/commands wiring,
  the dispatch shim, install/CLI) plus what they are meant to read (README, LICENSE, CHANGELOG,
  the runtime-read docs/MAKOTO-CONVENTIONS.md + docs/CITATIONS.md, and the README-linked
  SPIRIT.md + demo). The full falsifiability suite (~130 test files) lives in makoto-dev;
  public CI runs one self-contained end-to-end smoke test (catalog loads, install wires hooks
  + the ConfigChange manifest, a real forbidden-write deny and a clean allow on the wire).
  docs/CHAIN-FORMAT-v1.md moved to dev (not linked from anything shipped).
- **Stop-gate discovery unified for real; `GATE`/`StopCheck`/`load_stopchecks()` retired.**
  Every gate is now a plain `CHECK` (or `EXTRA_CHECKS` entry for contractOrder's dual
  Pre+Stop surface) discovered by `load_checks(edge="Stop")`, with the new structural
  `Check.may_block` field replacing GATE-export-presence as the blocking-eligibility
  signal -- two independent signals (may_block AND the Finding's own level), preserving
  the never-blocks guarantee for staleEstablisher/undeclaredFalsifiable by construction.
- **Repo now produced by an explicit allowlist sync from makoto-dev**
  (tools/restructure_public.py step_sync_from_dev in dev): every shipped file is named on
  the manifest and copied verbatim; dev-only features are stripped by asserted patches.
  Replaces the ignore-list/hand-patch mechanism whose July-8 "sync" silently diverged
  the repos in both directions.

### Removed (bedrock audit, 2026-07-10)
- `data/purpose.toml` (orphaned: claimed coverage-gating by files that do not exist),
  `docs/THREAT-MODEL.md` (zero references), the zero-caller `__init__.py` re-exports,
  `_dispatch._build_decision` and `session/commitments.retire_unsourceable_commitments`
  (production functions kept alive only by their own tests).
- Test-only tooling re-homed to `tests/`: `_fpHarness.py` (the `_hollowTestFpHarness.py`
  twin folded into it), `tools/rebuild_index.py`; `_testDelta.py` moved under
  `substrate/` (dispatch plumbing, not a root entry point). `data/` and `tools/`
  directories are gone.

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

### Added
- **One-command marketplace install** via `.claude-plugin/marketplace.json`, mirroring
  Detent's two-line install.

### Changed
- **Dispatch routing consolidated onto a `HANDLERS` row table.** `main()`'s per-event
  if/elif chain replaced by a plain dict lookup keyed on hook event name -- the same
  "capability is a row, never a branch" discipline as the runtime's other tables. No
  behavior change.

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
