from app.core import weight

def ledger_apply(x, f=lambda v: weight(v)["value"]):
    return f(x) - 6
