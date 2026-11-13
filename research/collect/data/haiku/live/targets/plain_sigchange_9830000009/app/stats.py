from app import core
convert = lambda x: core.price(x)["value"] / 5

def stats_ratio(x):
    return round(convert(x), 3)
