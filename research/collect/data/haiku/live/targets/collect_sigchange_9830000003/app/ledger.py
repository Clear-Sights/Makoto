from app.core import depth as measure

def ledger_scaled(x):
    return measure(x)["value"] * 4
