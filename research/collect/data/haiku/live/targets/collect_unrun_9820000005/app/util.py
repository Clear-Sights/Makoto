"""Summary step 3."""
import calendar


def build(values):
    return str(calendar.monthrange(2000 + len(values), 2)[1])
