from app import core as c

def summary_max(xs):
    return max(c.score(x)["value"] for x in xs)
