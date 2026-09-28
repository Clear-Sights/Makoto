<!-- Copied 2026-09-28 from the handoff's cross-pollination slice so a session reads its prior art here.
     The clones named at the bottom are inputs of START.md step 12 only; nothing here is read at launch. -->
# Cross-pollination slice: Makoto (from HANDOFF/sections/cross.md, 2026-09-28)

## Steps this slice feeds (cross.md G6; F conduct table; H rows 1-2)
1. One count, one home: Dev REGISTER.md has 88 ids; docs/REGISTER-MAP.tsv has 77 (63 RUNNER, 14 NOT-COUNTABLE); Scour
   reads 74 entries off Measure-Zero zero/resources/REGISTER.md; his 2026-09-22T02:05:06Z says "all 74 blindspots".
   Derive the map from the register file by script; every doc reads the count off the tool, never types it.
2. One owner per entry, by facet: join docs/REGISTER-MAP.tsv (runner per entry) with Scour's declined() reasons (facet each
   static probe lacks; scour/families/f1.py:179-187 and each family) into one table: static probe (Scour), dynamic runner
   (Makoto), or neither. Duplicates today: B7 (tools/merge_pass.py content.rule_without_runner vs Scour ref/runnable), B2
   (gate.hollow_test vs Scour --sweep), F2 (gate.pasted_fix vs Scour claim gate), D1. Keep the event side here.
3. The 14 NOT-COUNTABLE rows (docs/FOUNDATION-14.md:8-30): each names a runnable check or is removed. B37
   SIMPLER FORM UNSOUGHT and H4 SWEEP DRAWN FROM MEMORY are the two his conduct requirements would need (cross.md F).
4. Worth, measured: 125 fires, 2 catches, 4 true, 14 false, 105 repeats (README worth table); latency Pre 0.11 s, Post
   0.08 s, Stop 0.24 s. Repeats are the cost to cut first (E5/E10 identical_retry already exist; apply to own fires).
5. Conduct entries the handoff leans on: E5 UNBOUNDED RETRY, E10, E11 nested budget (churn); H6 gate.unclaimed_unit
   (bloat); H2 gate.stale_pass, D4 (stale awareness); I1, I2, I3 (dispatch brief, pin, unpaid acceptance); C7
   gate.completion (false done). All BLOCK-capable per REGISTER-MAP.tsv.
6. Makoto stays standalone (his 2026-09-24T22:56:42Z); the DetIO join is a ledger join: a catch inside hidden context
   is written as a row DetIO reads, no import either way.
7. docs/MERGE-WITNESSES.tsv rule (survivor's fix alone catches the dropped entry's trip) is the dedupe rule for the
   whole register and for Scour's probes (cross.md H row 2).

## Files to copy in or clone rows needed
- Scour clone (`Clear-Sights/Scour`): probes.declined() and REGISTER-MAP.tsv are the two halves of step 2.
- Measure-Zero clone: zero/resources/REGISTER.md is the register file; this repo's map derives from it.
- Courthouse (`Clear-Sights/Courthouse` README): Ward = act, Makoto = statement; install both in every launch checklist.
- Strong-Skills tools/treegen.py: skills generated from the register; the same generation replaces typed counts here.
