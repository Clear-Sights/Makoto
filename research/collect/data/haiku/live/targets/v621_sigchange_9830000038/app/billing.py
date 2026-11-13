from app import core
convert = lambda x: core.speed(x)["value"] / 2

def billing_ratio(x):
    return round(convert(x), 3)
