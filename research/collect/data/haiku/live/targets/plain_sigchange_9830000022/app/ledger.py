from app.core import weight

def ledger_total(xs):
    return round(sum(weight(x)["value"] for x in xs), 2)
