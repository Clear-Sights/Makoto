from app.core import margin

def ledger_total(xs):
    return round(sum(margin(x)["value"] for x in xs), 2)
