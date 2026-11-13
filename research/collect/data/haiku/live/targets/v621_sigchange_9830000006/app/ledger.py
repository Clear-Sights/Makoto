from app import core as c

def ledger_max(xs):
    return max(c.length_value(x) for x in xs)
