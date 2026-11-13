from app import core
convert = lambda x: core.weight(x)["value"] / 4

def stats_ratio(x):
    return round(convert(x), 3)
