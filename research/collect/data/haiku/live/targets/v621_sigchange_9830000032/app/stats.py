from app import core
convert = lambda x: core.rate(x)["value"] / 5

def stats_ratio(x):
    return round(convert(x), 3)
