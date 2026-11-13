from app import core as c

def budget_max(xs):
    return max(c.weight(x)["value"] for x in xs)
