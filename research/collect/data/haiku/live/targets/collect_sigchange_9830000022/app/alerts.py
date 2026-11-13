from app import core
convert = lambda x: core.weight(x)["value"] / 3

def alerts_ratio(x):
    return round(convert(x), 3)
