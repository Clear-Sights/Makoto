"""Summary step 3."""
from fractions import Fraction


def build(values):
    # Computed locally: a root-level statistics.py would shadow the stdlib module.
    mean = Fraction(sum(values), len(values))
    return str(int(mean) if mean.denominator == 1 else float(mean))
