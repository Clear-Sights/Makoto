# Round "set and probe": Makoto organised around the critical path. Committed before any code or run; never edited after.

Owner, 2026-11-12:
- "reorganize around the critical path";
- "the critical path is the shortest possible longest sequential path that gets whatever knowledge is required and leverages it";
- "we do not add mechanisms at all, we merely design them to naturally scale";
- "should we … automatically probe deterministically so that it doesn't block to begin with (isolated, of course, so nothing goes out)".

## The design
- **The critical path** of a session that changes something: input, edit, a run that succeeds, final answer. Makoto adds no link to it.
- **One fact, from the input:** at session start, the snapshot of the tree, and the lookup of which file uses which. A file uses another when an import-style line (`import`, `from`, `require`, `include`, `use`, `source`, `load`) names the other's module path or base name. The lookup is refreshed for files that change.
- **Sets, with no branch on size:**
  - changed = files that differ from the snapshot;
  - demanded = changed, plus every file that uses a changed file, through the lookup;
  - checked = files reached by a successful run that started after their last change. A run reaches the program it runs and everything that program uses.
- **One message:** it names demanded minus checked, and the entry programs that reach it.

## Two variants
- **set:**
  - after an edit, the message is a note, once per changed file until checked;
  - at the final answer, if demanded minus checked is not empty, the same message is a hold, once.
- **probe** (set, plus the automatic check):
  - **No note.** At the final answer, Makoto itself runs the entry programs that reach demanded minus checked.
  - **Isolation:** the probe runs in a temporary copy of the tree, with a scrubbed environment, closed input and no network (`unshare -rn` on Linux, `sandbox-exec` on macOS). Without network isolation there is no probe, and the variant behaves as set.
  - **What is probed:** only programs runnable with no argument by a known interpreter (python, node, ruby, perl, php, sh, bash). The copy is capped at 20,000 files and 50 MB, and each probe at 5 seconds.
  - **Pass:** the files it reaches are checked, and the final answer is admitted with no message.
  - **Fail:** a hold that carries the last 15 lines of the probe's output. At most 3 holds per final answer.

## Removed from 6.1.0
- The read-back payment for config files.
- The "same top-level folder" rule and the list of project-wide runners. A named test runner with no program argument reaches every file.
- The separate note and hold wordings, and the code and config file-type lists. A file is demanded when it is in the lookup or has a shebang.

## Checks before the live run
- **Tests, through the hooks.json command, with real files:**
  - width 0: a chat session, no message;
  - width 1: a script nothing uses;
  - width N: a module with three users. The note names them; a run of one user checks only what it reaches; a run of an entry program that reaches all of them checks all;
  - a failed run does not check;
  - probe: it passes silently; it fails with the output in the hold; without isolation it falls back; it writes nothing into the real tree and cannot reach the network.
- **No branch on size:** the code that computes the sets has no test of a set's length.

## Live (Haiku, CLI 2.1.322; same worker flags as before)
- **Families, 40 fresh tasks each:**
  - unrun level 3, seeds 9660000001 to 9660000040;
  - sigchange with 12 users (`gen_sigchange.py` of the replication), seeds 9670000001 to 9670000040.
- **Arms:** plain, mini (6.1.0, 68c050f), set, probe.
- **Kill test:** one probe call per family.
- **Analysis, per family:** exact McNemar; task bootstrap (10,000 resamples, seed 44) for pass differences and cost ratios; Holm over the three arms against plain.

## What ships
- **A variant replaces 6.1.0** when it meets all of these on both families:
  - it passes at least mini's count minus 4;
  - on sigchange it passes more than mini;
  - its cost ratio to plain is at most mini's.
- **If both qualify,** probe ships only when its cost ratio is below set's.
- **Otherwise** the owner decides.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| P1 | unrun pass (of 40): plain; mini; set; probe | 26; 35; 35; 36 | 18 to 32; 28 to 40; 28 to 40; 28 to 40 |
| P2 | sigchange pass (of 40): plain; mini; set; probe | 20; 21; 27; 27 | 12 to 28; 12 to 30; 16 to 36; 16 to 36 |
| P3 | unrun cost ratio to plain: mini; set; probe | 1.28; 1.28; 1.10 | 1.1 to 1.6; 1.1 to 1.6; 1.0 to 1.4 |
| P4 | sigchange cost ratio to plain: mini; set; probe | 1.3; 1.4; 1.2 | 1.0 to 2.0; 1.0 to 2.2; 1.0 to 2.0 |
| P5 | probe: share of final answers admitted with no message, unrun | 0.75 | 0.5 to 0.95 |
| P6 | probability that a variant ships | 0.45 | |
| P7 | `makoto2.py` lines: set; probe | 260; 330 | 180 to 380; 240 to 460 |
