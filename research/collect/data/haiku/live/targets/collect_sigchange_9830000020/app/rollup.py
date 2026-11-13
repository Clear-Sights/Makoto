from app import core as c

def rollup_max(xs):
    return max(c.margin(x)["value"] for x in xs)
