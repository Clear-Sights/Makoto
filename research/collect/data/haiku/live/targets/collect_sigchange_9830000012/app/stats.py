from app import core
convert = lambda x: core.weight_value(x) / 4

def stats_ratio(x):
    return round(convert(x), 3)
