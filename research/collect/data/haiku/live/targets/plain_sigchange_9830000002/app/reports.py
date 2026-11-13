from app import core
convert = lambda x: core.depth(x)['value'] / 4

def reports_ratio(x):
    return round(convert(x), 3)
