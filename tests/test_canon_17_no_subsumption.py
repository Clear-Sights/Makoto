"""Standing regression gate for the boolean-logic validation of THE_CANON_17
(checks/_canonAtoms.py). Encodes the 2026-07-09 proof: all 17 formulas satisfiable, zero exact
duplicates, zero subsumption pairs (no formula's literal-set is a superset of another's).

A subsumption pair would mean one formula's firing condition is redundant given another's --
this test exists so that fact stays checked on every future edit to THE_CANON_17, not re-derived
by hand. See docs/CANON-17-VALIDATION.md for the full narrative.
"""
from __future__ import annotations

from makoto.substrate._canonAtoms import THE_CANON_17


def test_canon_has_all_seventeen_formulas():
    assert len(THE_CANON_17) == 17


def _literal_set(formula: str) -> set:
    out = set()
    for lit in formula.split(" AND ") if " AND " in formula else formula.split("∧"):
        lit = lit.strip()
        neg = lit.startswith("NOT_")
        atom = lit[4:] if neg else lit
        out.add((atom, not neg))
    return out


def test_all_formulas_are_satisfiable():
    for name, formula in THE_CANON_17.items():
        lits = _literal_set(formula)
        atoms_seen: dict = {}
        for atom, polarity in lits:
            assert atoms_seen.get(atom, polarity) == polarity, (
                f"{name}: contradictory literal on atom {atom!r} -- formula is unsatisfiable")
            atoms_seen[atom] = polarity


def test_no_exact_duplicate_formulas():
    seen: dict = {}
    for name, formula in THE_CANON_17.items():
        key = frozenset(_literal_set(formula))
        assert key not in seen, f"{name} duplicates {seen.get(key)}'s formula exactly"
        seen[key] = name


def test_no_subsumption_pairs():
    lits = {name: _literal_set(f) for name, f in THE_CANON_17.items()}
    offenders = []
    for a, a_lits in lits.items():
        for b, b_lits in lits.items():
            if a != b and a_lits >= b_lits:
                offenders.append((a, b))
    assert offenders == [], (
        f"formula(s) subsume another -- redundant firing condition(s): {offenders}")
