"""Summary step 3."""


def build(values):
    # February length for the year 2000 + len(values); same result as
    # calendar.monthrange, without importing the stdlib `calendar` module
    # (which the root calendar.py would shadow when run from the root).
    year = 2000 + len(values)
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return str(29 if leap else 28)
