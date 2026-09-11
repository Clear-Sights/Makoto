# Makoto

[![CI](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml/badge.svg)](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml)

**An integrity hook for Claude Code that watches the agent's _own_ tool calls and blocks the ones
that fake a check.** When Claude says it did something — ran the tests, cited a paper, committed the
fix, verified the certificate — makoto holds that word against its record. If the deed isn't there,
or the verification was quietly disabled, makoto blocks the tool call (or the end-of-turn) and hands
the agent a one-line correction to retry against.

That publication claim is deliberately bounded: Shipped plugin — installable and versioned. The dispatcher is replay-tested against authored sessions; its effect on a live session's outcome is unmeasured.

**Integrity**, as this tool uses the word, is exactly that agreement: a claim the agent made this
turn is matched by the record of the deed it names. Nothing wider — not correctness, not code
quality, not whether the deed was a good idea. So `gate.relative_path_citation` says a bare
path is "a communication-quality signal, not an integrity violation": it contradicts no claim
against the record, it is only harder to follow. `makoto.vocab`'s `_INTEG_VOCAB` (vocab.py) is
the lexical half of the same idea — the word-set naming integrity concepts *in a subject's
code* — and is not a second definition of this one.

Checks declare their inputs in `registry.Check.eats`. Runtime outcomes are folded by
`verdict.apply`; receipt fields come from `state.ledger.emit_receipt`.

## What it catches

makoto fires on mechanical hook events — every `PreToolUse`, `PostToolUse`, and `Stop` — and
**blocks** on pre-check findings and blocking end-of-turn gate findings. The live inventory is:

<!-- BEGIN GENERATED: check-counts | source: makoto.registry | regenerate: python3 tools/render_checks.py --write -->

- **15 pre-checks**
- Pre-check ids grouped by dotted prefix — `content`: **12**, `event`: **2**, `gate`: **1**
- **23 Stop checks** (all checks registered at the Stop edge)
- **21 end-of-turn gates** (`may_block=True`)
- **17 blocking end-of-turn gates** (`registry.blocking_eligible`)
- **4 advisory end-of-turn gates** (advisory-allowlisted)

<!-- END GENERATED: check-counts -->

Two different things are called a *gate* in that list, and the counts are not comparable. The
`gate.` in a **pre-check id** is a naming prefix and nothing more; an **end-of-turn gate** is a
check registered at the Stop edge with `may_block=True`. The one pre-check carrying the prefix,
`gate.contract_order`, is not an end-of-turn gate — it has a same-named Stop sibling that is, and
the two are separate checks with separate predicates. Every count above is scoped by edge, so no
check is counted twice within a line.

**Verifier weakening** — a check silently neutered
- `content.verifier_predicate_weakened` loose-comparator verifier (`startswith`/`endswith`/`re.match` where `==` is meant)
- `content.verifier_exit_masking` exit-code masking (`|| true`, `; true`, `set +e` on a test/build/lint)
- `content.verifier_body_hollowed` hollowed verifier body (`return True` / `pass` in a constitution check)
- `content.env_gated_audit` audit/verification code gated behind an env var · `content.integrity_suppression_flag` integrity-named suppression flag (`*_skip = true`)

**Fabricated evidence** — a claim with no backing artifact
- `content.phantom_citation` phantom citation (Author-Year not in `makoto/docs/CITATIONS.md`)
- `content.unsourced_webfetch` WebFetch of a URL never seen in any prior tool result this session
- `content.fabricated_commit_sha` fabricated commit SHA/tag presented as proof of a commit
- `content.deferred_checkbox_theater` `DEFERRED`-style checkbox theater on an open to-do item
- `content.illusory_authorship_trailer` an illusory Claude/Anthropic authorship or generation attribution (trailer, session link, routing address, or "Generated with/by Claude" footer) — a plain "Claude Code" product-name mention is not matched
- `content.illusory_interruption_claim` a fabricated "interrupted by user" claim with no genuine harness-set interruption anywhere in this session's recorded history

**Self-defense**
- `content.self_mute_guard` makoto self-mute (disabling or un-wiring makoto via `settings.json`)

**Scope & contract discipline** — illusory progress and out-of-contract action (SPEC-5, ported by shape from Assay)
- `event.thrash_revert` a whole-file Write that reverts a file to an earlier byte-identical content after an intervening different Write (A→B→A, no net progress)
- `gate.contract_order` a result-producing call issued while a declared Plan's dependency for that step is still undischarged (its Stop-time sibling gate guards the remainder at turn end)

**End-of-turn gates** — fire on the agent's closing claims, checked against the recorded ledger.
[docs/CATALOG.md](docs/CATALOG.md) points to the registered checks and their implementations.

The **certification** column uses the following labels, each naming its own denominator:

- **established** — certified at zero false positives on the named negative sets: the shipped
  corpus for the ordinary blocking gates (the warning-tier-elimination invariant below — a
  pattern either blocks at proven zero corpus-FP, or it is cut), and additionally the
  planted-clean and real-Claude-gold negative sets for `gate.canon_fingerprints` (gold-oracle
  certification). Zero-FP on those sets is the claim; the live-session false-positive rate
  accumulates from field use and is not covered by it.
- **replayed** — a corpus replay ran but is inconclusive by the gate's own admission (the honest
  corpus almost never carries the triggering precondition), so certification rests instead on
  held-out adversarial RED fixtures plus that near-vacuous corpus-FP check.
- **advisory** — uncertifiable by design or not yet corpus-measured; recorded to the audit log,
  never emitted as a block decision.

| Check id | One-line trigger | Fire | Certification |
|---|---|---|---|
| `gate.completion` | "done / created `X`" but the artifact isn't on disk | blocking | established |
| `gate.advance` | advancing a phase whose precondition isn't recorded as met | blocking | established |
| `gate.green_claim` | "suite green" against a recorded test failure | blocking | established |
| `gate.dropped` | an identifying forward promise left undischarged at turn-end | blocking | established |
| `gate.fabricated_action` | "I ran `X`" in a turn with no tool call at all | blocking | established |
| `gate.named_test` | "`test_foo` passes" against a recorded `FAILED` of that named test | blocking | established |
| `gate.stale_pass` | "all tests pass" against pytest's own live `lastfailed` record | blocking | established |
| `gate.claimed_running` | "it's running/up" contradicted by this session's own Bash record | blocking | established |
| `gate.run_promised` | last turn promised a run ("I'll run the tests") and no Bash call followed | blocking | established |
| `gate.claimed_shipped` | "merged/pushed/live" with no successful remote-mutating call on record | blocking | established |
| `gate.claimed_consent_absent` | cites the operator's approval, instruction or word in a session whose transcript carries no genuine operator turn at all | blocking | new |
| `gate.unexamined_wall` | states that a fact cannot be determined when no action at all has been taken since the operator's last turn | blocking | new |
| `gate.liveness` | a statement with no live effect inside a closed function | blocking | established |
| `gate.hollow_test` | a test gutted so it can never fail (no assert, tautology, swallowed failure, uncollectable) | blocking | established |
| `gate.canon` | last call ended in an unresolved direct error, or a byte-identical stuck retry loop | blocking | replayed |
| `gate.canon_fingerprints` | ported canon fingerprints in the robust core established by gold-oracle certification | blocking | established |
| `gate.contract_order` | turn ends with a declared Plan's dependency remainder non-empty | blocking | established |
| `gate.self_wired` | makoto's own hook wiring partially stripped from `settings.json` | advisory | advisory |
| `gate.canon_fingerprints_advisory` | the advisory remainder (soft/claim atoms or gold-disqualified) | advisory | advisory |
| `gate.relative_path_citation` | a chat response citing a non-absolute (unclickable) path | advisory | advisory |
| `gate.plan_item_drift` | open plan/task-labeled commitments sourced from chat prose | advisory | advisory |

Inspect the pre-tool catalog with `makoto pattern list`; see one pattern in full with `makoto pattern show content.phantom_citation`.

<!-- BEGIN GENERATED: canon-split | source: makoto.substrate._canonAtoms | regenerate: python3 tools/render_checks.py --write -->

- blocking robust core: **4 of 17** ported canon fingerprints
- advisory remainder: **13** ported canon fingerprints

<!-- END GENERATED: canon-split -->

### Legitimately writing a flagged shape?

Follow the finding's retry hint; exemption scope belongs to the check.
See [Makoto conventions](plugin/makoto/docs/MAKOTO-CONVENTIONS.md) for the marker syntax.

```python
if os.environ.get("ENABLE_AUDIT_TRAIL"):  # makoto-allow: app feature, gates user-facing audit logging
    write_audit_trail()
```

## Install (plugin)

```
/plugin marketplace add Clear-Sights/Makoto
/plugin install makoto@makoto
```

Enabling the plugin wires the events declared in [hooks.json](plugin/hooks/hooks.json).
Its shim executes `python -m makoto.dispatch` from the plugin root.

State dir + `makoto.record.db` are created lazily on the first hook invocation.

### Companion setting (optional): suppress the harness auto-trailer

An illusory AI-authorship commit trailer can reach a commit through either path. Pre-Check `content.illusory_authorship_trailer` blocks
the **agent-authored** one — the trailer typed into a `git commit` message or into file content, the
surface no setting can reach. The other door is Claude Code's own **automatic** append, which a
setting governs. To close it at the source, set in `~/.claude/settings.json`:

```json
{ "includeCoAuthoredBy": false }
```

This is defense in depth, not a replacement: the setting closes the auto-append door, `content.illusory_authorship_trailer` closes
the agent-authored one. makoto's install does **not** write this for you — it leaves `settings.json`
untouched beyond hook wiring (above); set it yourself if you want the earlier layer.

### Migration from 0.3.0

If you previously ran the old `python -m makoto install` (0.3.0 or earlier), your
`~/.claude/settings.json` has makoto-managed hook entries. Running the plugin alongside would cause
double-dispatch. How to tell if you're affected: `grep makoto ~/.claude/settings.json` — any hit
means the old entries are present. Migrate cleanly:

```bash
python -m makoto uninstall                   # removes old settings.json entries
/plugin install https://github.com/Clear-Sights/Makoto  # installs the plugin
```

## Contributing

Reports are welcome and are credited by name; pull requests from outside this repository are not
merged. See [CONTRIBUTING.md](CONTRIBUTING.md) for why, and for what to send instead.

## Siblings

Makoto owns the statement surface alongside the independently installed engines for act and
sequence. None inherits or implies the others' coverage. The marketplace inventory is owned by
[Courthouse](https://github.com/Clear-Sights/Courthouse):
`claude plugin marketplace add Clear-Sights/Courthouse`.

| Engine | Judges | One line |
|---|---|---|
| [**Ward**](https://github.com/Clear-Sights/Ward) | the pending **act** | nothing outright bad happens |
| [**Keel**](https://github.com/Clear-Sights/Keel) | the **sequence** | a session neither capsizes nor gets lost |
| **Makoto** (this repo) | the **statement** | words aren't empty |

## Non-plugin install (power users)

```bash
pip install -e /path/to/makoto
# Then add makoto hook entries to ~/.claude/settings.json manually — see "Manual wiring" below.
```

The state dir and `makoto.record.db` are created lazily on the first hook invocation; there is no separate
init step.

## Uninstall

```bash
# Plugin install path:
/plugin uninstall makoto

# Non-plugin settings.json path:
python -m makoto uninstall   # removes makoto-managed settings.json entries
```

The state dir (`~/.claude/makoto_state/`) is preserved on uninstall — `audit.jsonl` and `makoto.record.db`
remain for forensic value. To fully reset, `rm -rf` the dir.

## CLI

```bash
python -m makoto status            # patterns loaded, hooks wired, state dir, any patterns muted
python -m makoto pattern list      # the full live catalog as a table
python -m makoto pattern show content.phantom_citation  # one pattern in detail
python -m makoto show src/auth.py  # ledger state for a normalized location key
python -m makoto install           # non-plugin: wire settings.json directly (prefer the plugin)
python -m makoto uninstall         # remove makoto-managed settings.json entries
```

## Manual wiring (fallback)

If you want to inspect or hand-wire what the plugin does, add to the `hooks.PreToolUse`,
`hooks.PostToolUse`, and `hooks.Stop` arrays of `~/.claude/settings.json`:

```json
{
  "matcher": "*",
  "hooks": [{"type": "command", "command": "python -m makoto.dispatch"}]
}
```

## Dispatcher outcomes

The shipped shim communicates findings using the measured response fields below. Invalid input is
the distinct process-error path.

<!-- BEGIN GENERATED: dispatch-contract | source: plugin/makoto/_dispatch_shim.sh | regenerate: python3 tools/render_checks.py --write -->

| Outcome | Observed mechanism | Process exit |
|---|---|---|
| clean PreToolUse call | no blocking decision | **0** |
| error-level pre-check finding | stdout JSON `hookSpecificOutput.permissionDecision='deny'` | **0** |
| Stop-gate finding | stdout JSON `decision='block'` | **0** |
| invalid/non-object payload | no blocking decision | **2** |

<!-- END GENERATED: dispatch-contract -->

## Fire level

`dispatch._OUTCOME_FOR_LEVEL` maps findings to outcomes; `verdict.apply` applies
`MAKOTO_MODE` and the oversight clamp. The wire tables determine which outcomes each hook emits.
The local-verifier branch of `content.verifier_exit_masking` can emit an advisory finding.

## Retry hints

Blocking findings carry their retry hints and conventions through `dispatch._emit_decision`
into the JSON response.

## Audit log

Firings append to `$MAKOTO_STATE_DIR/audit.jsonl`; clean dispatches do not.
The row schema is `state.audit.AuditRow`. Its `exit_code` records raw finding severity
in `dispatch._record_audit`, independently of the dispatcher's process exit.

### The error log

`$MAKOTO_STATE_DIR/dispatch_errors.jsonl` is the other half, and it is the half that matters when
something goes wrong: one row per predicate that raised and per dispatch-stage can't-evaluate. Every
row carries `plugin`, `session_id`, `tool_name`, `hook_event` and `id_source`.

Those fields were missing. `audit.jsonl` has carried the session and tool since 1.0.2 and this log
carried neither — so a *fire* was attributable and a *miss* was not, and every row here is a check
that did not run. When a batch of fail-opens landed together, "did they affect this session?" could not
be answered from the record. `id_source` says how the ids were obtained (`payload`, or `raw-scan`
when the envelope did not parse and they had to be recovered from the raw text); a recovered id
that does not admit it was recovered is worse than no id.

Row dispositions are `loud-allow` (a check did not run), `BLOCK`, `REPAIRED` (the envelope carried
bytes that had to be fixed, and evaluation then continued normally), and `NOTE`.

### Fail-open notices

`dispatch._emit_notices` reports buffered carriage faults when the host wire permits.
Check and audit failures retain their own reporting paths.

### Failure mode

Audit writes are best-effort. If the append fails (disk full, permission denied), dispatch prints one
stderr line and continues with its original exit code. The audit subsystem cannot cause makoto to
mis-block or mis-allow a tool call — a fundamental separation-of-concerns invariant.

## ConfigChange watch (advisory + evidence-gated blocking)

The optional `ConfigChange` command is `python -m makoto.configchange`; it is not shipped in
[hooks.json](plugin/hooks/hooks.json). It advises on missing wiring and blocks a strip only
when an install manifest or prior snapshot establishes that the exact path was wired.
`configchange._APPLICABLE_SOURCES` owns its source scope; unexpected faults fail open.

## Receipt: word → deed → record → receipt

The synthetic session in `docs/demo/` demonstrates the receipt chain:

1. **WORD**: the agent writes `src/auth.py`, then claims `"test_login passes now."` at Stop.
2. **DEED**: the write lands (`kind="touched"`); a test run fails (`kind="testrun"`,
   `FAILED tests/test_auth.py::test_login`); a fix lands; a second test run passes
   (`kind="testrun"`, `PASSED tests/test_auth.py::test_login`): three tamper-evident,
   hash-chained rows, each linked to the one before it.
3. **RECORD**: the test-delta redirect (Task 3) fires on the pass/fail flip and is ITSELF
   chain-appended (`kind="audit"`); the redirect's own firing is part of the permanent record,
   not just a line on someone's terminal.
4. **RECEIPT**: `makoto receipt --session demo-session-001` reports the measured claims and
   exemptions below; every claim is trace-bound to a `verify_chain`-checkable row:

```json
{
  "session_id": "demo-session-001",
  "verified_through": null,
  "claim_count": 2,
  "trace_bound_count": 2,
  "exemption_count": 0
}
```

The receipt cites the recorded test-run rows and their chain hashes.

### Reproduce it: corpus replay

`python3 eval/replay.py` from the repository root replays recorded sessions through the real
dispatcher. The executable summary below measures its derailment fixtures, total result, and
success contract.

### Live demo: real terminal sessions

`docs/demo/render_demo.py` drives the measured REAL scenarios through the actual dispatchers (not
the frozen corpus above) against a fresh, throwaway state dir each, and captures genuine stdout/stderr.

<!-- BEGIN GENERATED: demo-measurements | source: eval/replay.py + docs/demo | regenerate: python3 tools/render_checks.py --write -->

- corpus replay: **4 derailments**, **5/5** sessions pass; the command exits successfully only when every expectation holds
- live demo: **3 REAL scenarios**
- receipt demo: **2 claims**, **0 exemptions**

<!-- END GENERATED: demo-measurements -->

<img src="docs/demo/screenshots/block.svg" alt="a genuine PreToolUse block"><br>
<img src="docs/demo/screenshots/receipt.svg" alt="word -> deed -> record -> receipt, end to end"><br>
<img src="docs/demo/screenshots/configchange.svg" alt="a ConfigChange advisory fire">

Each SVG is rendered directly from that scenario's real logged stdout/stderr, not hand-written.

Regenerate: `python docs/demo/render_demo.py && python docs/demo/render_svg.py` (the latter needs
`humanize`, `pip install humanize`, for demo-only friendlier byte counts; never a core-package
dependency, see that script's own docstring).
