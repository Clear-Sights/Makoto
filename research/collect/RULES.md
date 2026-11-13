# Round "collect": Makoto runs the check itself, in Claude Code's sandbox. Committed before any code or run; never edited after.

Owner, 2026-11-13: "Read the ideal technique in hub and apply it"; "Why would you keep it off? If it works fully?"; "Doesn't Claude have a sandbox mode?"; "Sure".
- **Derivation:** `research/ideal/IDEAL.md`. Whether a program succeeds is a collected piece, and 6.2.1 has the model get it.
- **Sandbox:** `@anthropic-ai/sandbox-runtime` (`srt`, 0.0.83). A hook runs outside Claude Code's own sandbox, so Makoto calls `srt` itself.
  - Measured here: a probe could write inside its copy, could not write outside it, and could not open a connection; `srt` added 0.32 s.

## The change (on 6.2.2)
- **When:** after any completed tool call that leaves an unchecked demanded set, and again at the final answer if one remains.
- **What is probed:** the entry programs that reach the set, when each is runnable with no argument by a known interpreter (python3, node, ruby, perl, php, sh, bash) and reaches no outward-facing library through the map. The list is `research/set_probe/AMEND_1.md`'s.
- **How:**
  - the tree is copied to a temporary folder (at most 20,000 files and 50 MB);
  - one `srt` call runs the programs in that copy, in order;
  - the sandbox allows no network, and writes only inside the copy;
  - input is closed, and all the programs together get 8 seconds.
- **A result counts only for the tree it read.**
  - **Pass** (exit 0, no error marker): the nodes it reached are stamped, and nothing is said.
  - **Fail:** the message carries the last 15 lines of the output. It goes as a note after a tool call, once per distinct output for that program, or as the hold at the final answer.
  - **Timeout, or a program that cannot be probed:** 6.2.2's note and hold, unchanged.
- **Where it is on:** wherever `srt` runs, found on `PATH` or by `MAKOTO_SRT`. No setting turns it on. Without `srt`, Makoto behaves as 6.2.2.
- **State:** it stays the map. A node gains only the hash of its last noted failure.
- **Hook timeouts:** PostToolUse, Stop and SubagentStop are raised to cover the probe.

## Checks before the live run
- **Tests** (with `srt` where installed; skipped, and counted, where not):
  - a passing probe checks the change silently, and the final answer is admitted with no run by the model;
  - a failing probe puts the error in the note;
  - the same failure is not noted twice;
  - a probe cannot write outside its copy or reach the network, and the real tree is unchanged;
  - a program that reaches `subprocess` is not probed;
  - without `srt`, the behaviour is 6.2.2's.
- **6.2.2's tests** pass with `srt` absent.

## Live (CLI 2.1.323; `srt`, bubblewrap and socat installed)
- **Tasks:** 40 fresh tasks per cell: unrun level 3 and sigchange with 12 users, each on Haiku and on Sonnet. Seeds: 9820000001 to 40, 9830000001 to 40, 9840000001 to 40, 9850000001 to 40.
- **Arms:** plain, 6.2.2 (561c858) and collect.
- **Kill test:** one collect call per model; the stream must show a probe's effect.
- **Spend cap:** 40 USD.

## Ship rule
- **collect ships** when both of these hold in each of the four cells:
  - it passes at least 6.2.2's count minus 4;
  - its cost ratio to plain is below 6.2.2's.
- **Otherwise** the owner decides.

## Predictions (from `research/ideal/IDEAL.md`)
| id | quantity | point | range |
|---|---|---|---|
| I1 | Haiku pass, collect: unrun; sigchange (of 40) | 35; 35 | 28 to 40; 26 to 40 |
| I2 | Haiku cost ratio, collect: unrun; sigchange | 1.15; 1.20 | 1.0 to 1.35; 1.0 to 1.45 |
| I3 | Sonnet pass, collect: unrun; sigchange | 37; 38 | 30 to 40; 30 to 40 |
| I4 | Sonnet cost ratio, collect: unrun; sigchange | 1.20; 1.20 | 1.0 to 1.45; 1.0 to 1.5 |
| I5 | holds per run, collect: Haiku; Sonnet | 0.1; 0.3 | 0 to 0.5; 0 to 0.8 |
| I6 | share of collect runs with no model run of Python after the last change | 0.6 | 0.3 to 0.9 |
| I7 | probability that the ship rule holds | 0.45 | |
