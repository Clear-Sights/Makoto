from app import core
convert = lambda x: core.margin(x)["value"] / 7

def audit_ratio(x):
    return round(convert(x), 3)
