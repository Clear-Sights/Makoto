from app import core as c

def ledger_max(xs):
    return max(c.credit(x)["value"] for x in xs)
