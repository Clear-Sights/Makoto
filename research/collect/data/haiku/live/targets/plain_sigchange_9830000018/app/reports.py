from app import core
convert = lambda x: core.speed(x)["value"] / 5

def reports_ratio(x):
    return round(convert(x), 3)
