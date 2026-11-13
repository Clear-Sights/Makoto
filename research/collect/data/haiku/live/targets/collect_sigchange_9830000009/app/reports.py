from app import core as c

def reports_max(xs):
    return max(c.price(x)["value"] for x in xs)
