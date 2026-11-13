from app import core
convert = lambda x: core.weight(x)["value"] / 8

def budget_ratio(x):
    return round(convert(x), 3)
