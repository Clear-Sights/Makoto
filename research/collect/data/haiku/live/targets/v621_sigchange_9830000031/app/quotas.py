from app import core
convert = lambda x: core.margin(x)["value"] / 8

def quotas_ratio(x):
    return round(convert(x), 3)
