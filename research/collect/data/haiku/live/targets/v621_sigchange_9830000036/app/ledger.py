from app import core
convert = lambda x: core.speed(x)["value"] / 7

def ledger_ratio(x):
    return round(convert(x), 3)
