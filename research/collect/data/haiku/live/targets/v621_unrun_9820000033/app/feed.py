"""Summary step 3."""
import decimal


def build(values):
    return str(decimal.Decimal(sum(values)) / 4)
