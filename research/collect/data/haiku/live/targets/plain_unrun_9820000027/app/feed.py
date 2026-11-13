"""Summary step 3."""
from fractions import Fraction


def _mean(values):
    # Local replacement for statistics.mean: the root-level statistics.py
    # shadows the standard library module when running from the root.
    exact = Fraction(sum(values)) / len(values)
    return int(exact) if exact.denominator == 1 else float(exact)


def build(values):
    return str(_mean(values))
