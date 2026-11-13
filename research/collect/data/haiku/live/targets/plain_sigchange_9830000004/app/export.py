from app import core
convert = lambda x: core.score(x)["value"] / 7

def export_ratio(x):
    return round(convert(x), 3)
