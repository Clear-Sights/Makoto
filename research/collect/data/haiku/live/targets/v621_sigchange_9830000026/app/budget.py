from app import core
convert = lambda x: core.speed(x)["value"] / 3

def budget_ratio(x):
    return round(convert(x), 3)
