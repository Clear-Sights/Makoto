from app import core
convert = lambda x: core.length_value(x) / 2

def quotas_ratio(x):
    return round(convert(x), 3)
