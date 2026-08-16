# THE_CANON_17 boolean-logic validation

Exact propositional-logic analysis over `substrate/_canonAtoms.py`'s `THE_CANON_17` (17 formulas, pure
conjunctions over 13 boolean atoms). Regenerated live from the real catalog, not hand-transcribed:

```
formulas: 17
block-tier: 4
subsumption pairs found: []
```

- **Satisfiable**: all 17 formulas are satisfiable — none contains a contradictory literal on the
  same atom.
- **No exact duplicates**: no two formulas share an identical literal-set.
- **No subsumption**: no formula's literal-set is a superset of another's — meaning no formula's
  firing condition is logically redundant given another already in the catalog. This validates the
  catalog rather than finding waste.

This is genuinely checkable math (propositional logic over a finite, exhaustively enumerable
literal space), unlike the rest of the imperative codebase — techniques like Gosper's algorithm or
hypergeometric summation solve closed-form summation identities, not arbitrary control flow, and
would be empty rigor if forced onto this codebase's other logic.

Encoded as a standing regression gate in `tests/test_canon_17_no_subsumption.py` — re-run on every
change to `THE_CANON_17`, not re-derived by hand each time.
