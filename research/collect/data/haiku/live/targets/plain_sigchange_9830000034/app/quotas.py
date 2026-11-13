from app import core as c

def quotas_max(xs):
    return max(c.depth(x)["value"] for x in xs)
