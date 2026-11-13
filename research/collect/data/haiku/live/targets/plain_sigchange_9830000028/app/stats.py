from app import core as c

def stats_max(xs):
    return max(c.length(x)["value"] for x in xs)
