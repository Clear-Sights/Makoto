"""Summary step 3."""
from fractions import Fraction


def _mean(values):
    # Same result as statistics.mean for these inputs, without importing the
    # stdlib `statistics` module (a root-level statistics.py would shadow it).
    total = sum(Fraction(v) for v in values) / len(values)
    if any(isinstance(v, float) for v in values):
        return float(total)
    return total.numerator if total.denominator == 1 else float(total)


def build(values):
    return str(_mean(values))
