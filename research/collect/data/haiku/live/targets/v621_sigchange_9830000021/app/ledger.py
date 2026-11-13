from app import core as c

def ledger_max(xs):
    return max(c.credit_value(x) for x in xs)
