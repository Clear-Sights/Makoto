from app import core as c

def budget_max(xs):
    return max(c.depth(x)["value"] for x in xs)
