from app import core as c

def alerts_max(xs):
    return max(c.speed(x)["value"] for x in xs)
