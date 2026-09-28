# One mechanism per family, replacing per-case recognizers

Copied from the handoff section (2026-09-28) so a session reads it here.


Measured on main c11c483: `plugin/makoto` holds about 190 module-level lists and regexes. By file: spec.py 65, vocab.py 39, switch.py 30, lineage.py 25, otherPoint.py 16, _canonAtoms.py 14. These are per-case lifts: a case outside a list is ignored. The obligation core (`kit.unwitnessed`: a claim or act owes, and only a recorded event pays) is already one mechanism. The lifts sit in the *recognizers* that feed it. Four families, each with one replacement:

| family (examples) | per-case today | one mechanism | gap |
|---|---|---|---|
| effect of a command: read or write, destructive or not (`_BASH_READERS`, `_FIND_WRITING_ACTIONS`, `_is_destructive_argv`, scratch roots) | name lists of programs and flags | observe the effect. The hook records a digest of `git status --porcelain` (plus the mtimes of named paths) at Pre and at Post. "Wrote" and "destroyed" become recorded facts, not guesses from names | cost of the digest per call against the 2 s bound (unmeasured; inferred 10-50 ms); a writes-outside-the-repo blind spot, named |
| what counts as a verifier and its verdict (`_runner_segments`, `_CLEAN_REPORT_RX`, `_FAILING_REPORT_RX`, `_VERBOSITY_RX`, `_INFO_FLAGS`) | runner names plus report regexes | a verifier is any command key whose recorded exit code has been nonzero at least once in the session; its verdict is its exit code, never its text | exit codes of piped commands (pipefail absent) still need the masking row; measure fires on tools/corpus.py |
| claims in prose (benefit verbs, count claims, completion words, trailer strings) | one regex per row | one claim reader (`kit.claim`, step 7) returns (kind, subject, number); each row names only the event kind that pays its claim kind | the kind table itself is a vocabulary: bounded, one file, measured on the corpus |
| tool identity (`_DISPATCH_TOOLS`, mcp name heuristics) | tool-name lists | by input shape: a `prompt` input is a dispatch; a `file_path` plus content is a write | none known; small |

What cannot be made list-free: reading English claims. Family three shrinks it to one table in one file, with a corpus-measured false rate. A case Makoto claims but misses is then a defect in one mechanism, fixed once.

Placed as START.md step 13 (PR #104). Attack cases against the live rows (the attacker thread) become the plants: each is a violating case the per-case hook misses, and it must turn red under the mechanism.
