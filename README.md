# Makoto

**An integrity hook for Claude Code that watches the agent's _own_ tool calls and blocks the ones
that fake a check.** When Claude says it did something — ran the tests, cited a paper, committed the
fix, verified the certificate — makoto holds that word against its record. If the deed isn't there,
or the verification was quietly disabled, makoto blocks the tool call (or the end-of-turn) and hands
the agent a one-line correction to retry against.

It judges the agent against its _own_ utterances and record — never the world's truth. It holds no
facts ("France doesn't exist to it"); it only checks that a claimed word is kept, whole, and honored
in deed. A word it lets through becomes spendable: trustworthy tender a reviewer or another agent can
accept without re-deriving it.

## What it catches

makoto fires on mechanical hook events — every `PreToolUse`, `PostToolUse`, and `Stop` — and **blocks**
(exit 2, which Claude Code treats as block-and-retry) on **18 pre-checks** across four families and
**8 end-of-turn gates**. Every live check blocks; there is no silent "warning" tier (see
[Fire level](#fire-level)).

**Verifier weakening** — a check silently neutered
- `1.1` loose-comparator verifier (`startswith`/`endswith`/`re.match` where `==` is meant)
- `1.21` exit-code masking (`|| true`, `; true`, `set +e` on a test/build/lint)
- `1.27` hollowed verifier body (`return True` / `pass` in a constitution check)
- `1.2` audit/verification code gated behind an env var · `1.4` integrity-named suppression flag (`*_skip = true`)

**Fabricated evidence** — a claim with no backing artifact
- `1.6` phantom citation (Author-Year not in `docs/CITATIONS.md`)
- `1.9` WebFetch of a URL never seen in any prior tool result this session
- `1.22` fabricated commit SHA/tag presented as proof of a commit
- `1.5` `DEFERRED`-style checkbox theater on an open to-do item
- `1.34` an illusory AI-authorship commit trailer the agent never actually wrote

**Security-verifier disabling** — each a named CWE
- `1.26` / `1.29` / `1.33` TLS / peer-certificate verification disabled (`verify=False`, `CERT_NONE`)
- `1.28` / `1.31` JWT signature verification off / `none` algorithm whitelisted
- `1.32` paramiko SSH host-key check weakened to `AutoAddPolicy` · `1.30` timing-unsafe `==` on a secret/HMAC/digest

**Self-defense**
- `1.23` makoto self-mute (disabling or un-wiring makoto via `settings.json`)

**End-of-turn gates** — fire on the agent's closing claims, checked against the recorded ledger:
- `gate.completion` — "done / created `X`" but the artifact isn't on disk
- `gate.advance` — advancing a phase whose precondition isn't recorded as met
- `gate.green_claim` — "suite green" against a recorded test failure
- `gate.dropped` — a forward promise carrying identifying info ("I'll add `def X` to `Y`", "3 tests in `Z`") left undischarged at turn-end — said-but-not-done, checked against the agent's own touched-keys
- `gate.fabricated_action` — "I ran `X` / executed `Y`" in a turn with no tool call at all (presence-of-work, not command-text match)
- `gate.named_test` — "`test_foo` passes" against a recorded `FAILED` of that exact named test (coreference-pinned; the green_claim delta)
- `gate.stale_pass` — "all tests pass" against pytest's own `lastfailed` record still naming a live failing test (the runner's ledger, existence-filtered for staleness)
- `gate.liveness` — fires on the code itself, not a claim: a statement with no live effect inside a closed function (dead/illusory work the present-closure model can prove inert). It walks the turn's touched `.py` ASTs, so it yields a finding per illusory statement rather than one per turn.

Inspect the live catalog with `makoto pattern list`; see one pattern in full with `makoto pattern show 1.6`.

### Legitimately writing a flagged shape?

Annotate the line with `makoto-allow: <reason>` (any comment style, case-insensitive). makoto won't
fire on it, and your rationale is on the record — an auditable note, not a silent bypass.

```python
if os.environ.get("ENABLE_AUDIT_TRAIL"):  # makoto-allow: app feature, gates user-facing audit logging
    write_audit_trail()
```

**See [`docs/SPIRIT.md`](docs/SPIRIT.md)** — 誠 (makoto), the constitution every pattern derives from:
a word is real the way water is wet, a constitutive property, not an after-the-fact audit.


## Install (recommended: Claude Code plugin)

```bash
# In Claude Code:
/plugin install https://github.com/skill-labV2/Makoto
# (or a local clone path)
```

Claude Code reads `hooks/hooks.json` and registers `PreToolUse`, `PostToolUse`, and `Stop` hooks
pointing at `${CLAUDE_PLUGIN_ROOT}/_dispatch_shim.sh` automatically (which `exec`s
`python -m makoto._dispatch`). `~/.claude/settings.json` is NOT modified — the plugin system manages
its own hook registry.

State dir + `makoto.db` are created lazily on the first hook invocation.

### Companion setting (optional): suppress the harness auto-trailer

An illusory AI-authorship commit trailer reaches a commit through two doors. Pre-Check `1.34` blocks
the **agent-authored** one — the trailer typed into a `git commit` message or into file content, the
surface no setting can reach. The other door is Claude Code's own **automatic** append, which a
setting governs. To close it at the source, set in `~/.claude/settings.json`:

```json
{ "includeCoAuthoredBy": false }
```

This is defense in depth, not a replacement: the setting closes the auto-append door, `1.34` closes
the agent-authored one. makoto's install does **not** write this for you — it leaves `settings.json`
untouched beyond hook wiring (above); set it yourself if you want the earlier layer.

### Migration from 0.3.0

If you previously ran the old `python -m makoto install` (0.3.0 or earlier), your
`~/.claude/settings.json` has makoto-managed hook entries. Running the plugin alongside would cause
double-dispatch. Migrate cleanly:

```bash
python -m makoto uninstall                   # removes old settings.json entries
/plugin install https://github.com/skill-labV2/Makoto  # installs the plugin
```

## Non-plugin install (power users)

```bash
pip install -e /path/to/makoto
# Then add makoto hook entries to ~/.claude/settings.json manually — see "Manual wiring" below.
```

The state dir and `makoto.db` are created lazily on the first hook invocation; there is no separate
init step.

## Uninstall

```bash
# Plugin install path:
/plugin uninstall makoto

# Non-plugin / legacy settings.json path:
python -m makoto uninstall   # removes makoto-managed settings.json entries
```

The state dir (`~/.claude/makoto_state/`) is preserved on uninstall — `audit.jsonl` and `makoto.db`
remain for forensic value. To fully reset, `rm -rf` the dir.

## CLI

```bash
python -m makoto status            # patterns loaded, hooks wired, state dir, any patterns muted
python -m makoto pattern list      # the full live catalog as a table
python -m makoto pattern show 1.6  # one pattern in detail
python -m makoto show src/auth.py  # ledger state for a normalized location key
python -m makoto install           # legacy: wire settings.json (prefer the plugin)
python -m makoto uninstall         # remove makoto-managed settings.json entries
```

## Manual wiring (fallback)

If you want to inspect or hand-wire what the plugin does, add to the `hooks.PreToolUse`,
`hooks.PostToolUse`, and `hooks.Stop` arrays of `~/.claude/settings.json`:

```json
{
  "matcher": "*",
  "hooks": [{"type": "command", "command": "python -m makoto._dispatch"}]
}
```

Bracket the additions with `# makoto-managed-begin` / `# makoto-managed-end` markers for idempotent
removal.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No error finding. The tool call proceeds normally. |
| 2 | At least one error-level finding. Claude Code interprets exit 2 as block-and-retry: the tool call (or the turn, for a Stop gate) is blocked, the stderr diagnostic is surfaced to the agent as a tool-error message, and the agent retries with that feedback in context. |

## Fire level

Every live pattern blocks (`fire_level = "error"` → exit 2). makoto deliberately has **no
non-blocking tier**: a `warning`/`disabled` resting state — witnessing a violation and letting the
tool through — is itself an illusory word, the exact weakening shape makoto exists to catch. The
earlier three-tier system was removed in the 2026-06-02 *warning-tier-elimination* (a pattern either
blocks at proven zero corpus-FP, or it is cut).

## Retry hints

Each pattern carries a one-line, imperative `retry_hint` telling the agent what to do instead. When a
finding fires, the hint is printed on a second stderr line after the diagnostic:

```
[makoto ERROR] row 1.1 (verifier predicate weakened — loose-comparator shape): matched 'startswith(' at line 231
               retry: Use '==' for status comparison, not '.startswith()' / '.endswith()' / 're.match'. ...
```

## Audit log

Every dispatch appends one structured JSON line to `$MAKOTO_STATE_DIR/audit.jsonl` (default
`~/.claude/makoto_state/audit.jsonl`). It captures enough to triage true-positive vs. false-positive
without leaking whole-file contents. It's plain JSONL — query it with `jq` or any tool.

| Field | Description |
|---|---|
| `ts` | ISO-8601 UTC timestamp, microsecond precision |
| `event` | `live.pre_tool_use` \| `live.stop` (the firing events; `PostToolUse` is consumed for history) |
| `hook_kind` | Raw hook name from the harness |
| `tool_name` | The tool the agent invoked (`Write`, `Bash`, …) |
| `session_id` | Opaque session token |
| `project_root` | Absolute project root at invocation time |
| `pattern_fires` | List of pattern IDs that fired; `[]` if clean |
| `exit_code` | `0` (clean) \| `2` (finding emitted, block-and-retry) |
| `retry_hint_emitted` | Boolean — at least one fired pattern had a non-empty `retry_hint` |
| `findings` | Per-finding `{pattern_id, level, file, line, snippet}` |

### Failure mode

Audit writes are best-effort. If the append fails (disk full, permission denied), dispatch prints one
stderr line and continues with its original exit code. The audit subsystem cannot cause makoto to
mis-block or mis-allow a tool call — a fundamental separation-of-concerns invariant.
