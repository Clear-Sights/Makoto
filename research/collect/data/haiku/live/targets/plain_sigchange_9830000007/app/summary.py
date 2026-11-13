from app import core
convert = lambda x: core.credit(x)["value"] / 8

def summary_ratio(x):
    return round(convert(x), 3)
