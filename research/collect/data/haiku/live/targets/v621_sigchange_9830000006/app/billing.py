from app import core
convert = lambda x: core.length_value(x) / 8

def billing_ratio(x):
    return round(convert(x), 3)
