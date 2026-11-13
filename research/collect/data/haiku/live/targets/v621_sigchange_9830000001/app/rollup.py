from app import core
convert = lambda x: core.price(x)["value"] / 7

def rollup_ratio(x):
    return round(convert(x), 3)
