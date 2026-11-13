"""Summary step 3."""
from math import gcd


def build(values):
    # Equivalent to str(fractions.Fraction(sum(values), len(values))) for a
    # non-empty list, without importing the stdlib `fractions` module, which
    # the root-level fractions.py helper would shadow.
    total = sum(values)
    count = len(values)
    divisor = gcd(total, count)
    num, den = total // divisor, count // divisor
    return str(num) if den == 1 else f"{num}/{den}"
