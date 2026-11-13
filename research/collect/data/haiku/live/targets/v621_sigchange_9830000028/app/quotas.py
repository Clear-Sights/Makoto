from app import core
convert = lambda x: core.length(x)["value"] / 9

def quotas_ratio(x):
    return round(convert(x), 3)
