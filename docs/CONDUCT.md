# Conduct rows: what the grid prevents, and the J rows it does not yet carry

Copied from the handoff section (2026-09-28) so a session reads it here, not outside the repo.

## Conduct his 01:10Z message requires, and what prevents it (01:30Z)

Why 77 and not 74: the register had 74 entries. I1 to I3 (unbriefed dispatch, unpinned input, unpaid acceptance) were pasted in on 09-27 23:51Z from MAKOTO/REGISTER-PASTE.md (Makoto be2dbd9), and #100 counted them.

"Live" means a deterministic check that BLOCKS today (Stop) or DENIES (Pre). "Defined" means a new entry with its owes/pays and the gap that stops it landing now. Every defined row is held to the same three bars as the rest (deterministic, under the latency bound, worth.py >= on the corpus).

| his requirement | register entry | live? |
|---|---|---|
| no bloat before the finish | H6 FUNCTION DRAWN FROM NO CLAIM | live: gate.unclaimed_unit (a unit nothing asked for blocks) |
| | B37 SIMPLER FORM UNSOUGHT | defined (START.md step 7). Gap: a measured false rate |
| not diverted / divertable | F8, via gate.plan_item_drift | live: a committed plan item dropped without a word blocks |
| | D13, via gate.dropped | live |
| | G1 GOAL SUBSTITUTION | live: content.phantom_citation (evidence for a nearby easier question) |
| no waste | E5 / E10 UNBOUNDED RETRY | live: event.identical_retry |
| | E13 PARKED ON AN INHERITED CHANNEL | live: gate.relaunched_unchanged |
| | E11 NESTED BUDGET SHADOWED | live: event.nested_budget |
| | F8 STALE REFIRE (Makoto's own waste) | live since #101: unchanged findings are withheld |
| cannot get lost | G5 WALL WITHOUT INVENTORY | live: gate.unexamined_wall ("cannot" said with the means already held) |
| | G2 DETERMINED ASKED AS OPEN | live: gate.unasked_plan |
| | **J1 OFF-PATH ACT (new)** | defined. Owes: a Write/Edit/Bash write whose target is outside the current Countdown step's `inputs:`/owner paths. Pays: the step's row naming it, or a START.md edit adding it. Gap: the hook has no reader for the step row; it needs Dev handoff/check.py's tuple parser vendored as a Makoto input |
| never by hand what is deterministic | **J2 HAND REPEAT (new)** | defined. Owes: 3 or more Edit calls carrying the same old-to-new substitution in different files. Pays: one Bash run of a script or sed that applies it. Uses kit.neighbours on edit shapes, O(n·t). Gap: the threshold 3 is inferred; measure it on the corpus |
| never forget parallel | I1 UNBRIEFED DISPATCH | live: event.unbriefed_dispatch (covers the quality of a dispatch, not its absence) |
| | **J3 SERIAL INDEPENDENT (new)** | defined. Owes: 3 or more consecutive foreground Bash runs, each longer than T, with no file in common. Pays: a run_in_background run or an Agent dispatch among them. Duration = Post ts minus Pre ts; dispatch ingests every hook event, Pre included (dispatch.py:1031). Gap: T is unmeasured (inferred 30 s); the false rate on the corpus |
| never lose awareness of what it can do | G5 (above), E12 PRINCIPAL EXCLUDED | live: gate.unexamined_wall, content.self_mute_guard |
| never lose its objective | G1, C7 TRUNCATION AS COMPLETION, D1 WRITE UNVERIFIED | live: content.phantom_citation, gate.completion |
| know what it already created, how it works, where it belongs | H6 (above), F2 TWO SOURCES OF TRUTH, A3, H5 | live: gate.unclaimed_unit, gate.pasted_fix, gate.unread_structure, content.fabricated_commit_sha |
| no dupes: meaningful names, synonyms and shapes deduped | B7 / B21, via tools/merge_pass.py | live for Makoto's own checks only (every pair refuted) |
| | **J4 DUPLICATE SHAPE (new)** | defined. Owes: a Write/Edit introducing a def whose one-word name is a synonym of an existing def in the repo, or whose alpha-renamed AST shape equals one. Pays: a Read of that def's file before the write, or the new def replacing the old. Gap: the def index and synonym table (Dev `names.py code`, its 17 names); must fit the 2 s Stop bound |
| wiring and absences set before a line of code | **J5 UNSLOTTED UNIT (new)** | defined. Owes: a new def or file with no slot in the mesh wiring. Pays: its slot row exists before the write. Gap: the slot map (the Seed.v wiring from the mesh step) is not written yet, so J5 waits on it |

Order for the next Makoto session: J2 and J3 go after step 6's kit.neighbours; J4 after the names index; J1 and J5 when their inputs exist. Each lands like the 14: one commit that lowers a ratchet pin, catch and pass cases, measured rate.

## Token-eating methods and tiny diffs (his 01:39Z, answered 01:45Z)

Live today, blocking at Pre:
- E5 / E10: event.identical_retry catches re-runs of an identical command.
- E13: gate.relaunched_unchanged catches re-dispatching an unchanged subagent brief.
- D11: event.thrash_revert catches rewriting a file back and forth.
- F8: Makoto's own repeated findings are withheld (#101), and #102 adds the 3-block bound, the one-deny fanout exit, and a fail-open notice shown once per session.

No entry catches the rest. Each is defined below with its check and gap:

| row | owes | pays | gap |
|---|---|---|---|
| **J6 RE-READ** | a Read of a path and range already Read this session, with no Write/Edit to it since | a compaction between the two Reads (context was replaced), or a Write/Edit to the path | compaction is not in the store: register the PreCompact hook in hooks.json and record it; false rate on tools/corpus.py |
| **J7 CHUNKABLE EDITS** | N or more consecutive Edit calls to one file with no other tool between | one Write or MultiEdit carrying them, or a run between the edits (each state checked) | N inferred 4; measure on the corpus |
| **J8 SMALL-CALL LOOP** | N or more consecutive read-only calls (Read, Grep, Bash readers) with no act, each output under a size cap | one combined call, or an Agent dispatch that reads for it | N and the cap unmeasured (inferred 6 calls, 2 KB); J3 covers the serial-long-run half |

Each J row lands like the 14: one commit, catch and pass cases, the latency bound green, and worth.py at or above on the corpus.
