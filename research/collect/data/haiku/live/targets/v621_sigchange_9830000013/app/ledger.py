from app.core import credit as measure

def ledger_scaled(x):
    return measure(x)["value"] * 8
