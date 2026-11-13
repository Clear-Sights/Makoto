from app.core import speed as measure

def ledger_scaled(x):
    return measure(x)["value"] * 7
