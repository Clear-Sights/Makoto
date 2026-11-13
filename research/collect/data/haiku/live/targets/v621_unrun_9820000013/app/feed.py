"""Summary step 3."""


def _february_days(year):
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 29 if leap else 28


def build(values):
    return str(_february_days(2000 + len(values)))
