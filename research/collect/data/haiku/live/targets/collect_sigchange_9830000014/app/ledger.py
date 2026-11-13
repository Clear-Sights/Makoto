from app.core import rate as measure

def ledger_scaled(x):
    return measure(x)["value"] * 2
