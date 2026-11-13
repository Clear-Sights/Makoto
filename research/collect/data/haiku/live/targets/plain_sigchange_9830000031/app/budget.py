from app import core as c

def budget_max(xs):
    return max(c.margin(x)["value"] for x in xs)
