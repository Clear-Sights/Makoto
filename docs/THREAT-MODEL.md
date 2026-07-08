# Makoto threat model

What makoto defends against, what it doesn't, and why. Each line names the code or test that
makes it true, so this stays a checkable claim rather than a marketing page.

## In scope

- **Root-escape / protected-path prevention (preventive).** `event.forbidden_location`
  (`checks/forbiddenLocation.py`) is a `PreToolUse` deny check: it blocks a `Write`/`Edit`/
  `MultiEdit`/`NotebookEdit` whose target resolves outside the working directory, into a
  protected system/credential directory (`/etc`, `~/.ssh`, `~/.aws`, …), a shell rc file, or a
  credential-named basename, before the write happens. A pure lexical path check, no disk
  access.
- **Makoto self-mute prevention (preventive).** `content.self_mute_guard` blocks disabling or
  un-wiring makoto via `settings.json` content changes made through a tool call. Never
  exemptable, in-band or out: the seal on the mint cannot be signed by the would-be forger.
- **Hook-wiring partial-strip detection (detective, advisory).** `gate.self_wired` reads
  `.claude/settings.json` at every `Stop` and fires an advisory finding (never a block) naming
  which of makoto's own `PreToolUse`/`PostToolUse`/`Stop` entries is missing. This is a
  *partial*-strip detector: it needs at least one surviving entry to run at all, so it has **zero
  coverage** against a single edit that removes all three simultaneously. That edit also removes
  the very `Stop` entry that would have run the check (Claude Code reloads hook configuration
  live, not once at session start).
- **Full-strip detection (detective, evidence-gated blocking).** The `ConfigChange` watch
  (`_dispatch_configchange.py`, wired separately from `PreToolUse`/`PostToolUse`/`Stop`) is
  triggered by Claude Code's own file-watcher on `.claude/settings.json` edits, architecturally
  independent of the three hook entries it observes, so it **does** see a full simultaneous
  strip, unlike `gate.self_wired`. Two tiers: an unconditional advisory
  (`gate.configchange_advisory`) logs any settings edit that looks stripped, and a narrower
  blocking tier (`gate.configchange_transition`) fires only when there is independent evidence
  this exact settings path was genuinely wired before (an install-time manifest hit, or a prior
  observation of the same path with hooks present). A project makoto was never installed into is
  never blocked from editing its own settings, no matter how many times it evaluates as stripped.
- **Tamper-evident record.** Every dispatch, verdict, and receipt claim is appended to a
  hash-chained, append-only store (`ledger.py`; see `docs/CHAIN-FORMAT-v1.md`). A hand-edited row
  anywhere in the chain is detected: `verify_chain` names the exact broken link, not merely
  assumed intact.

## Out of scope

- **Anything outside a Claude Code session's own tool-call stream.** makoto judges the agent
  against its *own* utterances and record; it holds no facts about the world and does not
  validate the correctness of code, only whether a claim about that code matches the agent's
  recorded actions.
- **An edit made entirely outside any tool call** (a human hand-editing `settings.json` in a
  text editor while Claude Code isn't running). There is no hook event to observe it, only the
  next session's own checks (`gate.self_wired` at the next `Stop`, or `ConfigChange` if the
  editor triggers Claude Code's file watcher while a session is live).
- **A permission-mode-elevated session's added risk.** The hook payload's `permission_mode` field
  is captured (`GateContext.permission_mode`) but no check currently changes posture based on it.
  A stricter bar for `bypassPermissions`/`dontAsk` sessions is a documented future direction, not
  a current guarantee.

## What this adds up to

Two hook-wiring integrity layers, deliberately overlapping rather than redundant.
`gate.self_wired` needs no extra installation step and catches the common partial-strip case for
free, while the `ConfigChange` watch (opt-in, wired separately) closes the specific full-strip
gap the first layer cannot see by construction, without ever blocking a project makoto was never
installed into. Neither is preventive against a strip that happens outside a live session; both
exist to make a strip *visible* rather than to make it impossible.
