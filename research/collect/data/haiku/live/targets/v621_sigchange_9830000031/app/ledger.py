from app.core import margin as measure

def ledger_scaled(x):
    return measure(x)["value"] * 3
