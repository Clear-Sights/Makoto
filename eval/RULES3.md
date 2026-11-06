# Third round: read-before-edit and no misdirected findings (committed before any measurement of either change)

Order: (1) commit this file, the labeler support for the new rule and the replay field it needs; (2) build the
"before" figures on `ff63637`; (3) change 1 (read-before-edit) and measure; (4) change 2 (evidence) and measure.
Each change has tests that fail on `ff63637`. Corpus, plants and rules of rounds one and two are unchanged.

## Change 1: recall, the rule "an edited or overwritten file must have been read first"
- Rule `e`, shape `file`, enforces Original (Read the original instead of a derivation). A PreToolUse of Edit,
  MultiEdit or NotebookEdit, or of Write onto a file that already exists, is held when the session has neither read
  that file nor produced it earlier. A Write that creates a new file needs no reading.
- The hold names the rule and the missing reading and ends with `Clear: Read <path>.`
- "Exists": a live hook checks the file system. The replay has no files, so the converter records the log's own fact in
  `makoto.target_exists` on each Write PreToolUse (true iff that call's result has type `update`); an Edit
  always targets an existing file.
- Labels for rule `e`, S the path: `label.py` and `independent.py` both say the reading was present iff an earlier event
  read or produced S: a Read, Write, Edit, MultiEdit or NotebookEdit with `file_path` equal to S, or a Bash command
  containing S. Text that merely mentions S does not count for rule `e`.
- Target: Q1 plants caught 66 of 66, or each miss traced.

## Change 2: findings that name something present
- Text from the user prompt, and text the session itself wrote or got back from its own writes (its Write, Edit and
  MultiEdit inputs and their acknowledgements), count as evidence that a name is present. This replaces the rule that a
  path named in the prompt is not evidence (rule `e` now covers a file that must be read before it is edited).
- Target: the independent label's share of findings that name something present goes from 52 of 265 to 0, or each remaining
  one is traced. The three control tests of round two (a name nobody wrote or read is still held) stay green.

## Samples, seeds, measurements
- Fresh sample for the independent labeler: 60 holds, seed **20261107** (round two used 20261106), drawn from the
  results of each run with `eval/sample.py`; one sample per run, never redrawn.
- Runs: R0 = `ff63637`, R1 = R0 + change 1, R2 = R1 + change 2. Same 342 sessions; the same plants as round two
  (first-round P-plants and Q1/Q2/Q3), rebuilt from the converted corpus with the same admitted-step sets.
- Reported for R0, R1 and R2: holds; hold rate = holds / 2718 dependent steps; hold-level false positives by `label.py`
  (k of holds, Wilson 95%) and by the independent sample (k of 60, Wilson 95%); recall k/n with Wilson 95% by plant type
  (P1, P3, Q1, Q2, Q3); misdirected-finding share in the sample (findings the independent label finds present, k/n);
  errors; context bytes and ms per hook (`scripts/measure_cost.py`).

## Gate (for each change, against the run before it)
- no rise in hold-level false positives (`label.py` count);
- the independent sample's false-positive share stays at 0 of 60;
- recall does not fall (every plant type);
- errors stay at 0;
- items (b) to (d) still hold: the named action clears every held Stop (342 of 342 in the corpus), the user's prompt is
  never blocked, a corrupted journal does not block later steps.
If the new rule raises the hold rate, the rise and the false positives it adds are shown plainly.
