from app import core
convert = lambda x: core.length(x)["value"] / 5

def rollup_ratio(x):
    return round(convert(x), 3)
