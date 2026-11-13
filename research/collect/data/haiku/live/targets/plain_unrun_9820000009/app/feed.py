"""Summary step 3."""


def build(values):
    # February length for the year 2000 + len(values), computed inline so that
    # a root-level calendar.py does not shadow the standard library module.
    year = 2000 + len(values)
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return str(29 if leap else 28)
