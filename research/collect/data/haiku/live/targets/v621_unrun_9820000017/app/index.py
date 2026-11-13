"""Summary step 3."""
from math import gcd


def build(values):
    # Reduced fraction string, same output as str(fractions.Fraction(sum, len)).
    # Avoids `import fractions`, which would resolve to the root fractions.py helper.
    total = sum(values)
    count = len(values)
    if count == 0:
        raise ZeroDivisionError("mean of empty sequence")
    g = gcd(total, count)
    num, den = total // g, count // g
    return str(num) if den == 1 else f"{num}/{den}"
