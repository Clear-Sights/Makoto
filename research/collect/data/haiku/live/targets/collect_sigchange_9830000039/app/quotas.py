from app import core
convert = lambda x: core.length(x)["value"] / 2

def quotas_ratio(x):
    return round(convert(x), 3)
