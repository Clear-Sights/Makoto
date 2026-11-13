"""Summary step 3."""
from math import gcd


def build(values):
    # Formats sum/len in lowest terms, like str(Fraction(...)). Avoids importing
    # the stdlib `fractions` module by name, which the root fractions.py shadows.
    num, den = sum(values), len(values)
    g = gcd(num, den)
    num, den = num // g, den // g
    return str(num) if den == 1 else f"{num}/{den}"
