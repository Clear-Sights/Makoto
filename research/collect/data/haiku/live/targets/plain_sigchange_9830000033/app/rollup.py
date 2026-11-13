from app import core
convert = lambda x: core.weight(x)["value"] / 2

def rollup_ratio(x):
    return round(convert(x), 3)
