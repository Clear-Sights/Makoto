# Fourth round: the Downstream hold (committed before any measurement)

Order: (1) commit this file; (2) "before" figures on `b6de7fe`; (3) the rule and its tests; (4) "after" figures.
Principle and rule: Openness: "A more open input costs more to get right."; Downstream: "Account for every downstream
before moving upward." Basis: a change to one upstream function with 12 downstream users passed 32 of 60 plain, 60 of 60
with every downstream use listed by code (principles job 9, Haiku, sigchange, fitted).

## The rule (task-independent, deterministic, no model, no network)
- A name is changed when an admitted Edit, MultiEdit or Write on a source file changes or removes the line that defines
  it (`def`, `class`, or a module-level assignment): the old side of the call. For a Write the old side is the file as the
  session last read it; a Write over a file the session never read has no known old side.
- Its downstream is every line elsewhere in the working tree where the name occurs as a whole word, found by code
  (`git grep -w -n`, or a scan where git is absent). The changed file itself is not downstream.
- A downstream file is accounted for when the session read it after the change, or changed it.
- Checked before Stop, `git commit` and `git push`: hold while any downstream file of a changed name is unaccounted for.
  The hold names `Openness: Downstream`, the name, each unaccounted `path:line`, and ends `Clear: Read <path>.`
- A name with no downstream use holds nothing. Every existing behaviour is kept.

## Targets
- T1 plants of type D caught: every one, or each miss traced; their twins (every use file read, or none exists) admitted.
- T2 hold-level false positives: no rise on either labeler.
- T3 independent sample: 0 of 60 false positives.
- T4 recall on the earlier plant types (P1, P3, Q1, Q2, Q3) does not fall.
- T5 errors 0. Hook cost (context bytes, ms per hook) reported, no target.

## Plant type D (and its twin)
A corpus session with a Write or Edit that changes a definition line having a downstream use in another file: D removes
every reading of one use file made after the change (and keeps the others); the twin keeps that reading. The plant is
applied at the Stop, as for the earlier types. Sessions with no such definition change cannot carry D and are counted as
not eligible, not as misses.

## Samples, seeds
- Fresh sample for the independent labeler: 60 holds, seed **20261108** (rounds two and three used 20261106 and
  20261107), drawn with `eval/sample.py`, one sample per run, never redrawn.
- Runs: R0 = `b6de7fe`, R1 = R0 + the Downstream hold. The 342-session corpus of Clear-Sights/Tiller-from-the-Ashes,
  branch `principles`, read-only, as #172 used; rebuilt with the same admitted-step sets and the same earlier plants.
- Reported for R0 and R1: holds; hold rate over dependent steps with Wilson 95 %; holds the rule adds; hold-level false
  positives by `label.py` and by the independent sample (k/n, Wilson 95 %); recall k/n with Wilson 95 % by plant type
  (P1, P3, Q1, Q2, Q3, D and twin); errors; context bytes and ms per hook (`scripts/measure_cost.py`).
- Labels for the new rule on both labelers: the finding is true iff the named file has a whole-word use of the name and
  no reading or write of that file after the definition change appears in the session.

## Gate (against R0)
- no rise in hold-level false positives on either labeler;
- the independent sample's false positives are 0 of 60;
- recall on earlier plant types does not fall;
- errors 0;
- earlier guarantees hold: every held step is clearable by the named action, UserPromptSubmit is never blocked, a
  corrupted journal blocks only a step whose reading is lost.

## If the corpus cannot be read
If the corpus repository cannot be attached read-only, the corpus items are reported as blocked and not worked around;
the rule and its tests (synthetic sessions) are still delivered, and nothing above is reported as measured.
