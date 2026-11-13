from app import core
convert = lambda x: core.length(x)["value"] / 8

def billing_ratio(x):
    return round(convert(x), 3)
