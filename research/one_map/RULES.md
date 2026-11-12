# Round "one map": all of Makoto's state on one map. Committed before any code or run; never edited after.

Owner, 2026-11-12:
- "why are we doing full files instead of i/o chains?";
- "I wonder if the mapping can actually simulate it … I dislike that things like that can grow, however we can literally attach it to the map, instead of doing things independently";
- "1, build one map and ship it".

## The design (built on set, 856a5cf; no probe)
- **The map is the only state.**
  - **Node:** one per file under the working directory. It holds the file's size and modified time at session start, the start time of the last successful run that reached it, whether its last reaching run failed, and whether its note was given.
  - **Link:** from a file to a file it depends on. There are three kinds, all read from the files' text:
    - **uses:** an import-style line names the other file (set's rule);
    - **reads:** a quoted string names another project file by relative path or base name with extension;
    - **produced by:** the same, on a line with a write marker (`>`, `>>`, a `'w'` or `'a'` mode, `write`, `dump`, `save`, `to_csv`, `to_json`). This link points from the data file to the file that writes it.
  - Links are refreshed for files that change.
- **No run is kept.** A successful run stamps its start time on every node it reaches, and is forgotten. A failed run sets the failed flag on them.
- **The state never grows with the session.** Its size is bounded by the tree's files and links.
- **Sets, with no branch on size:**
  - changed = nodes that differ from their session-start size or time, plus new files;
  - demanded = the runnable or linked changed nodes, plus every node that reaches a changed one. A changed file is runnable when it has a known interpreter's extension or a shebang; this fixes set's linkless gap;
  - checked = nodes whose stamp is later than the latest change among the changed nodes they reach.
- **One message:** as in set, a note after an edit and a hold once at the final answer.

## Checks before the live run
- **Tests, through the hooks.json command:**
  - set's tests;
  - a linkless changed script is held;
  - the data chain: a script that writes `out.json`, and another that reads it. Changing the writer demands the reader; a run of the reader alone, after the writer ran, checks both ends;
  - the state file is the same size after 200 recorded runs as after 2.
- **State file:** no list of runs, reads, notes or unpaid files is in it.

## Live (Haiku, CLI 2.1.322)
- **Tasks:** 40 fresh tasks per family: unrun level 3, seeds 9680000001 to 9680000040; sigchange with 12 users, seeds 9690000001 to 9690000040.
- **Arms:** plain, mini (6.1.0), set, one map.
- **Kill test:** one call per family.

## Ship rule
- **one map ships as 6.2.0** when all of these hold on each family:
  - it passes at least the better of mini and set, minus 4;
  - its cost ratio to plain is at most set's plus 0.05.
- It must also pass more than plain on sigchange.
- **Otherwise** the owner decides.

## Predictions
| id | quantity | point | range |
|---|---|---|---|
| Q1 | unrun pass (of 40): plain; mini; set; one map | 27; 35; 33; 35 | 18 to 33; 28 to 40; 26 to 40; 28 to 40 |
| Q2 | sigchange pass: plain; mini; set; one map | 25; 21; 36; 36 | 15 to 32; 12 to 30; 28 to 40; 28 to 40 |
| Q3 | cost ratio to plain, one map: unrun; sigchange | 1.25; 1.28 | 1.1 to 1.5; 1.1 to 1.6 |
| Q4 | `makoto2.py` lines (set: 379) | 340 | 250 to 420 |
| Q5 | probability that the ship rule holds | 0.6 | |
