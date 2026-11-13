"""Summary step 3."""
import math


def build(values):
    # Formats sum/len as a reduced fraction, matching str(fractions.Fraction(...)).
    # Done locally because the root-level fractions.py shadows the stdlib module.
    num, den = sum(values), len(values)
    if den == 0:
        raise ZeroDivisionError("division by zero")
    g = math.gcd(num, den)
    num, den = num // g, den // g
    if den < 0:
        num, den = -num, -den
    return str(num) if den == 1 else f"{num}/{den}"
