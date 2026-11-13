from app import core as c

def summary_max(xs):
    return max(c.rate(x)["value"] for x in xs)
