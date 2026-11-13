from app import core
convert = lambda x: core.depth_value(x) / 7

def stats_ratio(x):
    return round(convert(x), 3)
