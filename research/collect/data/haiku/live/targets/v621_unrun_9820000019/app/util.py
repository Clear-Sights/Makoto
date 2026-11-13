"""Summary step 3."""
from fractions import Fraction


def build(values):
    # Mean computed here rather than via the stdlib `statistics` module, because
    # a root-level statistics.py shadows it when show.py runs from the root.
    # Mirrors statistics.mean: an exact integer mean prints as int, else float.
    m = Fraction(sum(values), len(values))
    return str(m.numerator if m.denominator == 1 else float(m))
