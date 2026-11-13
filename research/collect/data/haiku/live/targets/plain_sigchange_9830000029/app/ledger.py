from app import core
convert = lambda x: core.volume(x)["value"] / 3

def ledger_ratio(x):
    return round(convert(x), 3)
