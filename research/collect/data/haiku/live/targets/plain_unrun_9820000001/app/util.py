"""Summary step 3."""


def _days_in_february(year):
    # Same result as calendar.monthrange(year, 2)[1], without importing the
    # stdlib `calendar` module, which the root-level calendar.py shadows.
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 29 if leap else 28


def build(values):
    return str(_days_in_february(2000 + len(values)))
