from app import core
convert = lambda x: core.depth(x)["value"] / 9

def rollup_ratio(x):
    return round(convert(x), 3)
