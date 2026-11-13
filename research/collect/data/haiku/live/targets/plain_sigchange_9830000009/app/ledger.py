from app.core import price as measure

def ledger_scaled(x):
    return measure(x)["value"] * 9
