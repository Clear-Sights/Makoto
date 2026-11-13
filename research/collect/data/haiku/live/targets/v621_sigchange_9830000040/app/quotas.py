from app import core
convert = lambda x: core.rate(x)["value"] / 6

def quotas_ratio(x):
    return round(convert(x), 3)
