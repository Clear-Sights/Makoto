from app.core import speed

def ledger_total(xs):
    return round(sum(speed(x)["value"] for x in xs), 2)
