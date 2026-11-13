from app import core
convert = lambda x: core.credit_value(x) / 6

def rollup_ratio(x):
    return round(convert(x), 3)
