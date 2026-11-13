from app import core as c

def billing_max(xs):
    return max(c.length(x)["value"] for x in xs)
