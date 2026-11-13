from app import core
convert = lambda x: core.credit(x)["value"] / 6

def rollup_ratio(x):
    return round(convert(x), 3)
