"""Summary step 3."""


def build(values):
    # Days in February of the year 2000 + len(values). Computed directly so
    # this module does not import the stdlib `calendar`, which the root
    # calendar.py helper would shadow when show.py runs from the root.
    year = 2000 + len(values)
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return str(29 if leap else 28)
