from app import core
convert = lambda x: core.depth(x)["value"] / 5

def ledger_ratio(x):
    return round(convert(x), 3)
