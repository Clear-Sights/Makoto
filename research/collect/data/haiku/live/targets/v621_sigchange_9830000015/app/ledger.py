from app import core as c

def ledger_max(xs):
    return max(c.score(x)["value"] for x in xs)
