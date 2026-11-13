"""Summary step 3."""
import fractions


def build(values):
    return str(fractions.Fraction(sum(values), len(values)))
