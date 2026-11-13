from app import core as c

def reports_max(xs):
    return max(c.rate(x)["value"] for x in xs)
