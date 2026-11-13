from app import core
convert = lambda x: core.price(x)["value"] / 8

def reports_ratio(x):
    return round(convert(x), 3)
