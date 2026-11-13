from app.core import weight

def ledger_apply(x, f=lambda x: weight(x)["value"]):
    return f(x) - 6
