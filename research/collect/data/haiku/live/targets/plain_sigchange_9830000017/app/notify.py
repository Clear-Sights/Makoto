from app import core
convert = lambda x: core.depth(x)["value"] / 7

def notify_ratio(x):
    return round(convert(x), 3)
