from app.core import length_value

def ledger_total(xs):
    return round(sum(length_value(x) for x in xs), 2)
