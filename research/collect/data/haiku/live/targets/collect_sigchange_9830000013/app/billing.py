from app import core as c

def billing_max(xs):
    return max(c.credit(x)["value"] for x in xs)
