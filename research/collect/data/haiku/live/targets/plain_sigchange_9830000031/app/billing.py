from app import core as c

def billing_max(xs):
    return max(c.margin(x)["value"] for x in xs)
