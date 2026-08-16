# Self-defense asymmetry follow-up (Phase 1b open ticket) — verdict: OPEN

**Ticket text being closed out:** "fix the self-defense asymmetry (§4) — Makoto's
`precheck_1_23` only recognizes its own disable shapes; since both now install plugin-only,
settings.json's role in either's self-defense is largely moot, so this can downgrade to
'confirm plugin-only closes it, document, done' rather than a code change."

**Verdict: the downgrade premise is false for this repo. The asymmetry is not closed — it is
OPEN**, for two independent reasons found by reading the actual code and the actual install
state, not by re-deriving the original assessment's claim.

## 1. This repo is not plugin-only — settings.json is the live vector

`TOOL_STACK_ASSESSMENT.md` §4's "cleanest fix" (push both to plugin-only install) has not been
applied here. The real, current `.claude/settings.json` (repo root) wires Makoto directly:

```
PreToolUse:  matcher "*" -> command "python3 -m makoto._dispatch"
PostToolUse: matcher "*" -> command "python3 -m makoto._dispatch"
Stop:        matcher "*" -> command "python3 -m makoto._dispatch"  (+ ventura hook_bridge)
SessionStart: session-start.sh + ventura hook_bridge
```

Makoto does carry a plugin manifest (`makoto/.claude-plugin/plugin.json`, v1.4.0) but this repo
is not using it — the live hook wiring is the legacy settings.json path the ticket assumed was
moot.

Separately, and more surprisingly: **Assay has no entry in this settings.json at all.** Assay's
own installer (`assay/assay/adapters/claude_code.py:51`, `HOOK_MODULE =
"assay.adapters.hook_bridge"`) identifies its hook entries by that command substring
(`_is_assay`, line 71-73); no such string appears anywhere in the real settings.json. So in this
repo, right now, Assay's live hook is not wired in at all — only Makoto's dispatch runs on
PreToolUse/PostToolUse/Stop. That makes settings.json unambiguously the live, real attack
surface for Makoto's self-defense today, not a legacy path Assay is quietly covering.

## 2. Even granting the general "Assay covers settings.json" argument, it only covers four tools — not Bash

`TOOL_STACK_ASSESSMENT.md` §4 says Assay's `forbidden_location` band "denies *any* edit to
`.claude/settings.json` outright, content-blind." That phrasing is imprecise in a way that
matters here. Reading `assay/assay/patterns/forbidden_location.py`:

- `applies_to_tools = _WRITE_NAMES | _EDIT_NAMES` where `_WRITE_NAMES = {"Write", "MultiEdit"}`
  and `_EDIT_NAMES = {"Edit", "NotebookEdit"}` (lines 134-135, 160).
- `check_call` returns a clean pass immediately if `call.name not in _WRITE_NAMES and
  call.name not in _EDIT_NAMES` (line 181-182).
- The engine mirrors this: `_LOCATING_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")`
  (`assay/assay/runtime/engine.py:86`).

**`Bash` is not in this set, anywhere.** A grep of every pattern file under
`assay/assay/patterns/` (`forbidden_location.py`, `contract_order.py`, `drift.py`,
`grammar_instances.py`, `stale_establisher.py`) for `"Bash"` turns up nothing — no Assay pattern
inspects Bash command content at all. So "denies any edit to settings.json" is only true for
edits made via the four structured tool calls; a Bash-issued edit (`sed -i`, a `python3 -c`
one-liner, `cat > .claude/settings.json <<EOF ... EOF`, etc.) is invisible to Assay's monitored
surface regardless of what it writes.

## 3. Makoto's own `precheck_1_23` has the identical Bash blind spot — not just "wrong disable shapes"

Reading `makoto/prechecks/precheck_1_23.py`: the predicate only inspects
`current_event["tool_input"]["file_path"]` (line 62) and matches it against `_SETTINGS_RX`
(line 28: `\.claude/settings(?:\.local)?\.json$`). A `Bash` tool call's `tool_input` is
`{"command": "..."}` — it carries no `file_path` key at all, so `_SETTINGS_RX.search(fp)` never
matches and the predicate returns `None` unconditionally (line 63-64) before it even reaches the
disable-shape checks (env var, `_makoto_managed`, `disableAllHooks`, command-gut). This is
confirmed by `makoto/tests/test_pattern_1_23.py`: every fire/inert test constructs a `Write`,
`Edit`, or `MultiEdit` payload (`_pre(...)`, `tool_name="Write"` default) — there is no test at
all exercising a `Bash`-shaped `tool_input`, because the predicate has no code path for one.

So the real gap is broader than the ticket's framing ("only recognizes its own disable
shapes"): `precheck_1_23` doesn't fail to recognize *foreign* disable shapes so much as it never
looks at Bash-originated edits *at all*, regardless of whose hook entries they target. This was
true before Phase 1b and remains true now; nothing in the plugin-vs-settings.json question
changes it, because the gap is in which *tool call shape* the predicate reads, not in which
*install path* is active.

## Net effect: a concrete, still-open bypass

Today, in this repo: an agent (or a compromised/careless one) can run, via `Bash`:

```
sed -i '/makoto._dispatch/d' .claude/settings.json
```

(or the `python3 -c` / heredoc equivalent) to strip Makoto's `PreToolUse`/`PostToolUse`/`Stop`
entries from the live settings.json, leaving the `ventura` entries untouched, and:

- Assay's `forbidden_location` does not fire — `Bash` is not a monitored tool name (§2 above),
  and Assay isn't even wired into this repo's hook chain to be asked (§1 above).
- Makoto's own `precheck_1_23` does not fire — the event has no `file_path` to match against
  (§3 above).
- No other pattern in either catalog inspects Bash command text for `settings.json`,
  `makoto_state`/`dispatch.sh`, or `_makoto_managed` (checked: `precheck_1_21.py`,
  `precheck_1_22.py`, `precheck_1_34.py` are the only Makoto prechecks that reference `Bash` at
  all, and none reference settings.json content).

This is a realistic edge case, not a contrived one — Bash is a normal, frequently-used tool, and
"edit a config file via a shell one-liner" is an ordinary move, not an exotic attack.

## What would actually close this (out of scope here — code change, future ticket)

1. Going plugin-only for both tools (the original "cleanest fix") would remove settings.json as
   an attack surface **only if** it also removes Makoto's ability to be re-wired via
   settings.json at all — i.e., the fix has to be "Makoto refuses to also honor a
   settings.json-based install" or "there is no settings.json entry to strip," not just
   "plugin.json exists." Right now plugin.json existing does not stop the settings.json wiring
   also being present and live, as this repo demonstrates.
2. Independently of install path, closing the Bash blind spot requires either (a) a new
   Assay/Makoto pattern that inspects `Bash` `tool_input.command` text for edits touching
   `.claude/settings.json` / `.claude/settings.local.json` (structurally hard: shell command
   parsing to find a target path is a much fuzzier surface than `file_path` structural args), or
   (b) moving the hook wiring to a location outside the agent's writable/shell-reachable
   surface, or (c) a POST-hoc integrity check (hash/signature over the installed hook config,
   verified independently of the in-session tool-call stream) rather than a PRE-hoc content
   predicate.

None of this is implemented as of this doc. Do not treat this ticket as closed by "plugin-only
install" — that premise does not hold in this repo's actual state, and even where it would hold,
it would not close the Bash-tool gap described above.

## Citations

- `.claude/settings.json` (repo root) — actual install state, no `assay.adapters.hook_bridge`
  entry, Makoto wired via `PreToolUse`/`PostToolUse`/`Stop` -> `python3 -m makoto._dispatch`.
- `makoto/.claude-plugin/plugin.json` — Makoto's unused-in-this-repo plugin manifest.
- `assay/assay/adapters/claude_code.py:51,71-73` — `HOOK_MODULE` / `_is_assay` identify Assay's
  own hook entries by command substring; absent from this repo's settings.json.
- `assay/assay/patterns/forbidden_location.py:134-135,160,181-182` — `_WRITE_NAMES`,
  `_EDIT_NAMES`, `applies_to_tools`, and the tool-name guard in `check_call`.
- `assay/assay/runtime/engine.py:86` — `_LOCATING_TOOLS = ("Write", "Edit", "MultiEdit",
  "NotebookEdit")`.
- `makoto/prechecks/precheck_1_23.py:61-64` — reads `tool_input["file_path"]` only; no `file_path`
  key on a `Bash` call means immediate silent return.
- `makoto/tests/test_pattern_1_23.py` — every test constructs a `Write`/`Edit`/`MultiEdit`
  payload; no `Bash`-shaped case exists.
- `TOOL_STACK_ASSESSMENT.md` §4 (lines 222-228, 288-289) — the original finding and the "push
  both to plugin-only" recommendation this ticket was downgraded against.

## 2026-07-05 update — partial-strip detection added as mitigation, verdict stays OPEN

**Verdict: still OPEN.** What follows is mitigation, not closure — see the "what would actually
close this" list above, which is unchanged; direction (c) (an out-of-band integrity check) is
still required to close this ticket.

**What was added.** A DESIGN DECISION (the repo's designated one-shot decision-maker for
oversight-config/claim-bearing changes, invoked because this touches `.claude/` self-defense
posture) authorized Option 1 from that decision's own menu: implement a narrow self-check,
recorded explicitly as mitigation, not closure. The result is `gate.self_wired`
(`makoto/stopchecks/stopcheck_self_wired.py`, registered like every other Stop gate via the
`stopcheck_*.py` auto-discovery in `makoto/stopchecks/__init__.py:load_stopchecks`). At each Stop
event it reads `.claude/settings.json` (repo-root-relative, same convention as `gate.dropped`'s
`fs_read` calls) and fires an **advisory-only** finding (`level="advisory"`, never `"error"` —
`_dispatch.py`'s `_build_decision` only escalates `level=="error"` findings to a block, so this
never blocks a turn) naming which of PreToolUse/PostToolUse/Stop is missing a makoto-dispatching
entry.

**Real coverage, stated precisely.** This check catches a *partial* strip — an edit that removes
at least one of Makoto's three hook entries while leaving another intact — and records it to the
audit log for a later session (or a later Stop event in the same session, if something re-wires
Makoto's Stop hook in between) to see. It does not catch, and does not claim to catch, the
canonical *full* strip of all three entries in one edit.

**Corrected finding — no same-session grace period for a full strip.** The decision that
authorized this check initially speculated that "Claude Code captures hook configuration at
session start... the Stop-time check would fire once, in-session, even against the canonical full
sed strip." **This speculation was checked against Claude Code's own documentation
(code.claude.com/docs/en/settings.md, "When edits take effect") and found FALSE:** hooks
configuration is file-watched and reloaded **live** during the session, not cached once at
session start. This means a same-session `sed -i` (or equivalent) strip of all three of Makoto's
hook entries takes effect essentially immediately, *including* the Stop entry that would have run
`gate.self_wired` — so the removed Stop entry never runs again to report the removal. The check
gets **zero** same-session grace period against the canonical full-strip attack described in §"Net
effect" above; it was never live to observe it in the first place. Coverage is limited to: (a) a
partial strip (at least one Makoto-dispatching entry survives to report the loss of another), or
(b) a full strip discovered only if some later event re-wires Makoto's Stop hook before the next
Stop fires (an unusual sequence, not the attacker's easiest path).

**Closure still requires direction (c).** As stated above and unchanged by this update: closing
this ticket for real requires the out-of-band integrity check — a hash/signature over the
installed hook config, verified independently of the in-session tool-call stream, so that a full
simultaneous strip is detectable by something that was never itself disabled by the strip. `gate.
self_wired` is not that; it is an in-session, in-band advisory signal that is honest about its own
blind spot (see the check's own module docstring, which states this limitation as its first line).

## 2026-07-05 followup — researched direction (c); one real candidate found, not built (rule-4)

**Verdict: still OPEN, and now precisely bounded.** This section researched, against Claude Code's
own current documentation, whether *any* built-in mechanism exists that is independent of the
in-session PreToolUse/PostToolUse/Stop dispatch chain and could deliver direction (c) (an
out-of-band integrity check). One real, currently-documented candidate was found —
**`ConfigChange`**, described below. It was **not built**: doing so means adding a new hook entry
to `.claude/settings.json`, which is itself hook wiring in oversight config — a rule-4 trigger this
repo's `CLAUDE.md` requires escalating to a design decision, not something a dispatcher/worker
builds unilaterally. So the ticket's status is unchanged (OPEN), but the reason it's open is now
"a real fix exists and needs a decision," not "nothing exists."

### What was checked, and what was not found

- **No built-in integrity check on `.claude/settings.json` content.** Checked
  `code.claude.com/docs/en/settings.md` directly: no hashing, signing, checksum, or
  cryptographic-attestation feature over settings files is documented anywhere. The only
  loss-prevention feature is generic and unrelated to tamper detection: "Claude Code automatically
  creates timestamped backups of configuration files and retains the five most recent backups to
  prevent data loss" (`settings.md`). Backups protect against accidental loss; they do not alert
  anyone to a strip, and nothing reads or diffs them automatically — recovering from one, if it
  even applies to this JSON, is a manual, out-of-band action a human would have to think to take.
- **No permission gate on editing `.claude/settings.json` itself.** Checked the same page: the
  `permissions` object governs what *Claude's tool calls* may do, not who may edit settings files;
  there is no settings-file-specific write-approval step documented.
- **No hook event fires "outside" the dispatch mechanism entirely** in the sense of a periodic/
  heartbeat timer independent of any trigger — every event in the reference
  (`code.claude.com/docs/en/hooks.md`, "Hook lifecycle" table) is tied to *some* occurrence
  (session start/end, a turn, a tool call, a subagent, a compaction, a config file changing, a
  worktree, etc.), not a bare clock tick. `SessionEnd` ("when a session terminates") is the closest
  thing to a session-boundary catch-all, but Makoto has no entry under any lifecycle event other
  than PreToolUse/PostToolUse/Stop today (confirmed by re-reading `.claude/settings.json`: its
  `SessionStart` array has only `session-start.sh` and `ventura`/`assay` `hook_bridge` entries — no
  `makoto._dispatch` anywhere in it), and adding one is the same rule-4 problem as everything else
  in this section.

### The one real candidate: `ConfigChange`

`code.claude.com/docs/en/hooks.md` and `.../hooks-guide` (verified independently across three
separate fetches, schema identical each time) document a hook event that does not exist inside the
PreToolUse/PostToolUse/Stop per-tool-call chain at all:

> `ConfigChange` — "When a configuration file changes during a session." Matcher filters by
> `config_source`: `user_settings`, `project_settings`, `local_settings`, `policy_settings`, or
> `skills`. Input fields: `config_source` and `config_path` (absolute path to the changed file) —
> no diff, no old/new content. Decision control: return `{"decision": "block"}` or exit code 2 to
> **"[block] the configuration change from taking effect"** — except for `policy_settings`, which
> "must take effect immediately" and cannot be blocked.
> (hooks-guide, "Audit configuration changes"; hooks reference, "ConfigChange" section and its
> exit-code-2 table.)

This is architecturally different from everything discussed above: it is triggered by Claude Code's
own file-watcher on the settings file itself (`settings.md`: "Claude Code watches your settings
files and reloads them when they change... the `ConfigChange` hook fires for each detected
change"), not by an agent's tool call being dispatched through Makoto's own `_dispatch`. A single
`sed -i` that strips all three of Makoto's `PreToolUse`/`PostToolUse`/`Stop` entries in one write is
still, from Claude Code's own perspective, one detected change to `project_settings` — exactly the
event `ConfigChange` exists to catch. And unlike `gate.self_wired` at `Stop`, its documented
behavior is **blocking, not advisory**: a `ConfigChange` hook can refuse to let the edit take
effect at all, in-session.

**What this would still need, and the one thing I could not confirm from documentation alone.** The
docs state *that* blocking prevents the change from taking effect but not the precise ordering
guarantee this ticket's closure hinges on: is the hook set consulted for a given `ConfigChange`
event the one registered *before* that change (so a single edit that guts Makoto's `ConfigChange`
entry along with everything else still gets evaluated by the pre-strip, Makoto-inclusive hook set,
because the strip hasn't been adopted into the live config yet), or could a sufficiently-crafted
single edit race past its own detector? The "prevents the change from taking effect" phrasing is
the strongest evidence for the former (a check that could be silently pre-empted by the very change
it exists to catch would make the advertised blocking behavior meaningless for exactly the case it
is presumably meant to protect against — audit/compliance edits to hook config), and it also is not
documented as an explicit contractual guarantee anywhere I could find in `hooks.md`,
`hooks-guide.md`, `settings.md`, or the TypeScript SDK reference (`agent-sdk/typescript.md`, which
does not expose a fuller `ConfigChangeHookInput` definition than the JSON schema already quoted
above). This would need empirical verification (a scratch/sandboxed test: register a `ConfigChange`
hook, have it try to strip itself and Makoto's other entries in a single edit, confirm whether it
still fires and can still block) before anyone should rely on it as a closure mechanism rather than
a promising, unverified one. It also would not, by itself, guarantee the on-disk file gets reverted
— "blocks... from taking effect" most plausibly protects the *live, in-memory* hook set for the
rest of the session, which is exactly this ticket's stated harm ("disables Makoto for the rest of
the session"), but says nothing about whether a stripped-but-blocked file would still be read fresh,
un-remediated, at the next session's `SessionStart` — a gap that would need Makoto's own
(not-yet-existing) `SessionStart` entry to close, which is itself the same rule-4 problem again.

### Candidate for a future design decision (not built here)

**What it is:** add a `ConfigChange` hook entry to `.claude/settings.json`, matcher `project_settings`
(or `""` to also cover `local_settings`), dispatching to a new Makoto entry point (or extending
`makoto._dispatch` to handle a `ConfigChange` event shape it does not currently receive — confirmed
by inspection that `makoto/_dispatch.py`'s dispatch table, built for PreToolUse/PostToolUse/Stop
event shapes, has no branch for `hook_event_name == "ConfigChange"` today) that: reads
`config_path`, checks whether all three Makoto-dispatching entries (PreToolUse, PostToolUse, Stop)
are still present, and — if this is meant to be a real fix rather than another advisory mitigation —
returns `{"decision": "block"}` when they are not.

**What it would take:**
1. A design decision authorizing new hook wiring in `.claude/settings.json` (rule-4: hook wiring) —
   and, separately, a design decision on whether the new check is advisory (matching current
   `gate.self_wired` posture) or blocking (rule-4: enforcement tiers/defaults; this would be the
   first Makoto check that ever blocks rather than merely reports).
2. Empirical verification of the ordering question above, ideally *before* the design brief is
   written, so the decision is made on a confirmed mechanism rather than a plausible-sounding one.
3. A decision on whether the on-disk-revert gap (last paragraph above) is acceptable to leave to a
   companion `SessionStart` entry (itself rule-4) or must be closed in the same change.

**Why this is escalated, not built:** both the new hook entry and any move to blocking-by-default
are named verbatim in this repo's `CLAUDE.md` rule 4 ("oversight config (`.claude/`, hook wiring,
enforcement tiers/defaults)") as things dispatchers and workers must surface upward, never decide or
build themselves.

### Corrected verdict

**OPEN — genuinely unclosable from within Makoto's own current hook wiring without a rule-4
escalation, but no longer open for lack of a known mechanism.** A real, currently-documented Claude
Code feature (`ConfigChange`) exists that is independent of the PreToolUse/PostToolUse/Stop
per-tool-call stream, fires on the exact file-level event this ticket's attack requires, and is
documented as blocking-capable rather than merely advisory — meaningfully stronger than what
direction (c)'s original "hash/signature" framing anticipated, and a plausible way to close this
ticket for real. It was not built here because doing so requires new hook wiring in
`.claude/settings.json` and, if made blocking, a change to enforcement defaults — both squarely
rule-4 oversight-config triggers under this repo's `CLAUDE.md`, not a dispatcher/worker-level build.
The candidate above is precise enough that a future design decision could act on it directly,
provided the ordering question is verified empirically first.

### Citations (this update)

- `code.claude.com/docs/en/hooks.md` and `code.claude.com/docs/en/hooks` — full hook lifecycle
  table (confirms no bare periodic/heartbeat event exists; every event ties to an occurrence);
  `ConfigChange` section: input schema (`config_source`, `config_path`), decision control
  (`{"decision":"block"}` / exit code 2), and the `policy_settings` exception.
- `code.claude.com/docs/en/hooks-guide` — "Audit configuration changes" worked example, matching
  schema and blocking behavior independently confirmed against the reference page.
- `code.claude.com/docs/en/settings.md` — "Claude Code watches your settings files and reloads them
  when they change... the `ConfigChange` hook fires for each detected change"; automatic
  timestamped-backup feature (last five, generic loss-prevention, not tamper-detection); confirms
  no hashing/signing/permission-gate feature exists for settings files.
- `code.claude.com/docs/en/agent-sdk/typescript` — checked for a fuller `ConfigChangeHookInput`
  definition; none beyond the JSON schema already documented in `hooks.md` was found.
- `.claude/settings.json` (repo root, re-read for this update) — confirms Makoto's `SessionStart`
  array entry still does not exist; only `session-start.sh` and `ventura`/`assay` `hook_bridge`
  entries are present under `SessionStart`.
- `makoto/_dispatch.py` — confirms no `ConfigChange`-shaped event branch exists in the current
  dispatch table; this event type would need new handling code, not just new wiring, if ever built.

## 2026-07-05 followup — detection logic built and tested; wiring/enforcement still pending, verdict unchanged

**Verdict: still OPEN, unchanged from the previous section.** This update adds ONLY the pure
predicate the candidate above described — the code that decides "does this settings change strip
Makoto's hook wiring" — as ordinary, testable project source with no hook registration and no
`.claude/settings.json` change of any kind. It does not close this ticket, because the two rule-4
acts the previous section identified (wiring a `ConfigChange` entry into `.claude/settings.json`,
and the advisory-vs-blocking enforcement-tier decision) are both still outstanding and both still
require direct human/main authorization, not a dispatcher/worker build. This landing was dispatched
directly from main as a fresh, explicit ticket scoped in advance to exclude both of those acts —
distinct from, and not a workaround for, the reshaped mid-task chat-relay request the previous
section correctly declined.

**What was built:** `makoto/configchange_verdict.py` — a pure function,
`configchange_verdict(event, *, settings_json=None, fs_read=None) -> ConfigChangeVerdict`, that
takes a `ConfigChange`-shaped payload (`config_source`, `config_path`, per the schema this doc
already verified against Claude Code's docs above) plus the settings file's own content (either
pre-parsed JSON or a `path -> str` reader, caller's choice, documented in the function's own
docstring) and returns a frozen `ConfigChangeVerdict` dataclass: `applicable` (is this
`config_source` even capable of carrying Makoto's hook wiring — only `project_settings`/
`local_settings` are), `evaluated` (was the content actually readable/parseable), `stripped` (does
it lose >=1 of PreToolUse/PostToolUse/Stop's makoto-dispatching entry), `missing_events`, a single
actionable `fires` boolean (`applicable and evaluated and stripped`), and a `reason` string. **No
`fire_level`/advisory-vs-blocking field exists on the verdict, by design** — that decision is left
for whichever future hook adapter a design decision authorizes to map `fires` onto, not decided here.

Detection logic is reused, not re-duplicated a third time: `configchange_verdict` imports
`_missing_makoto_events` directly from `makoto/stopchecks/stopcheck_self_wired.py:31-38` (byte-for-
byte the same predicate `gate.self_wired` uses), rather than hand-copying it the way
`stopcheck_self_wired.py` itself was forced to hand-copy from `install.py` (its own module-top
comment explains why: the `stopchecks` package's gate-module layering firewall,
`makoto/tests/test_gate_shape.py`'s `ALLOWED_IMPORT_ROOTS`, restricts what a *gate* module may
import — it does not restrict a non-gate module from importing a gate module's helpers, and
`makoto/tests/test_stopcheck_self_wired.py` already establishes that exact precedent). This module
lives outside `makoto/stopchecks/` entirely (not a `stopcheck_*.py` file, no `GATE` export, not
discovered by `stopchecks/__init__.py:load_stopchecks`) specifically so it is not auto-registered as
a live gate and cannot fire in any real session.

**Test coverage** (`makoto/tests/test_configchange_verdict.py`, 19 tests, all against constructed
payloads — no live `ConfigChange` event exists to test against, stated explicitly in both the module
docstring and the test file's own header): a clean fully-wired `project_settings` change (verdict:
does not fire) and the same for `local_settings`; a partial strip of one event (fires, names it);
**a full simultaneous strip of all three events (fires — this is the headline case: unlike
`gate.self_wired`'s Stop-time blind spot, a pre-change `ConfigChange`-shaped check CAN see a full
strip about to happen, because it is triggered by Claude Code's own file-watcher independent of
whichever of Makoto's own hooks the strip removes)**; three unrelated `config_source` values
(`user_settings`, `policy_settings`, `skills` — not applicable regardless of how stripped the
content is, including a case where the content IS fully stripped to prove `config_source` gates
first); a missing `config_source` key; five content-unavailable fail-open edge cases (no content
source at all, `fs_read` returning `None`, `fs_read` raising, malformed JSON, non-dict JSON, and a
`hooks` key of the wrong shape treated as "missing all three"); managed-flag entries counting as
wired (mirrors `install.py`/`gate.self_wired` semantics); `settings_json` taking precedence over
`fs_read` when both are supplied (proven by an `fs_read` stub that raises if called); `fs_read`
receiving the event's exact `config_path`; an attribute-object event shape in addition to a plain
dict; and a `reason` string present on every verdict shape. Confirmed these two new files, once
git-tracked, do not themselves trip `gate.liveness`'s own corpus false-positive check
(`makoto/tests/test_liveness_fp.py::test_fp_zero_on_makoto_source`).

**What remains, unchanged:** exactly the two items the previous section named — (1) a design decision
authorizing a new `ConfigChange` hook entry in `.claude/settings.json` (rule-4: hook wiring), and
separately (2) a design decision on advisory vs. blocking (rule-4: enforcement tiers/defaults) — plus
the still-unverified ordering guarantee (does the hook set consulted for a `ConfigChange` event
predate the change it's evaluating) that should be checked empirically before either design brief is
written. Do not treat this ticket as closed: the detection logic existing and being tested is
necessary but not sufficient — nothing reads `configchange_verdict` from any real event today, and
without the wiring decision nothing ever will.

### Citations (this update)

- `makoto/configchange_verdict.py` — the new pure predicate and `ConfigChangeVerdict` dataclass;
  module docstring states the "not wired, not live, verified only against constructed payloads"
  limitation explicitly.
- `makoto/tests/test_configchange_verdict.py` — 19 tests, all against constructed payloads.
- `makoto/stopchecks/stopcheck_self_wired.py:19-38` — `_entry_dispatches_to_makoto`/
  `_missing_makoto_events`, imported (not re-duplicated) by the new module.
- `makoto/tests/test_gate_shape.py` (`ALLOWED_IMPORT_ROOTS`, `EXPECTED_GATE_FILES`) — confirms the
  gate-module layering firewall does not apply to (and the new module is deliberately kept outside)
  the `makoto/stopchecks/` package, so it is never auto-discovered as a live gate.

## 2026-07-22 update — `gate.self_wired` now checks two wiring sources, not one

**What changed.** `self_wired_gate` read only `.claude/settings.json`'s own `"hooks"` key. A
plugin-packaged Makoto install (this repo's own distributed form: `hooks/hooks.json` inside the
plugin, resolved at runtime via `${CLAUDE_PLUGIN_ROOT}` and never duplicated into the consuming
project's `settings.json`) produced the identical "all three missing" signal a genuine full strip
would — every turn, permanently, for any project using the plugin as intended. The check's own
docstring already named this exact ambiguity ("this check cannot and does not try to distinguish
'never wired' from 'just stripped'") but had not been extended to resolve it. Confirmed live in a
real session: `gate.self_wired` fired identically on every Stop event for 3+ hours against a
project whose Makoto wiring was, in fact, fully intact via the plugin manifest the whole time.

**The fix.** `_missing_makoto_events` now takes an event still missing from settings.json and
gives it one more chance against the plugin's own `hooks/hooks.json`, checked with the SAME
rigor as the settings.json side (`event_wired`, hoisted to `substrate/wiring.py` alongside
`entry_dispatches_to_makoto` so both sources share one predicate). An event only reports missing
if NEITHER source confirms it — a genuine partial strip across both sources still fires exactly
as before.

**The one load-bearing invariant, per a strongest-model consult run before this landed (this is a
security-relevant change to the self-defense surface, gated on that consult per this repo's own
standing model-escalation policy):** the plugin root MUST resolve via the live `$CLAUDE_PLUGIN_ROOT`
environment variable alone — the same pointer Claude Code substitutes into
`${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh` at actual hook-invocation time — never a guessed
or cached path. A fixed/searched path is gameable (an attacker plants a decoy manifest the check
trusts without it being the live wiring); `$CLAUDE_PLUGIN_ROOT` is self-consistent with the real
dispatch, so spoofing the check's view means relocating the real install, not silencing it. On any
resolution or read failure (unset root, unreadable file, malformed JSON, non-dict payload), the
plugin-manifest side fails CLOSED — contributes nothing, never treated as confirmation — so the
check degrades toward alarm, never toward silent-wired. This does NOT close the check's own
documented blind spot above: it still reads disk state at check time, not the harness's live-
loaded hook table, and a genuine simultaneous strip of both sources at once remains undetectable
by construction (disabling the check checks itself in the same instant, same as before).

**Parked, not implemented (a further hardening the consult noted but which this fix does not
need):** the fact that `self_wired_gate` is executing AT ALL when invoked as a real Stop hook is
itself forge-proof, live confirmation that at least the `Stop` event is genuinely wired right now
— strictly stronger evidence than any file read. A future pass could record "have I observed
myself fire on event E this session" (the audit log already carries `hook_kind` per event) and use
a positive observation to suppress that event's finding outright, falling back to the anchored
file-based check only for not-yet-observed events. Not built here to keep this change to the one
well-scoped, well-tested gap it targets; noted so it isn't silently lost.

### Citations (this update)

- `makoto/substrate/wiring.py` — `event_wired`, `read_plugin_manifest_hooks`,
  `PLUGIN_MANIFEST_RELPATH` added alongside the existing `entry_dispatches_to_makoto`.
- `makoto/checks/selfWiredCheck.py` — `_missing_makoto_events` and `self_wired_gate` both take
  optional `plugin_root`/`plugin_fs_read` (default: live `$CLAUDE_PLUGIN_ROOT` / a real file read),
  preserving the existing `fs_read`-injection pattern for testability.
- `makoto/tests/test_self_wired_check.py` — 15 new tests: plugin-manifest-alone coverage, genuine
  two-source strip still firing, fail-closed on unreadable/malformed/absent plugin manifest, exact
  path resolution (`<root>/hooks/hooks.json`), and direct coverage of the two new `wiring.py`
  helpers. Full suite (1380 tests) and the pinned `test_stop_gate_level_invariant.py` both green.
- `makoto/tests/test_gate_shape.py` — `EXPECTED_FUNCTION_COUNTS["selfWiredCheck.py"]` pin updated
  2->3 for the one new top-level helper (`_default_plugin_fs_read`), a real count change, not drift.
