from app import core
convert = lambda x: core.volume(x)["value"] / 7

def summary_ratio(x):
    return round(convert(x), 3)
