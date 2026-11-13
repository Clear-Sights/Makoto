from app import core as c

def reports_max(xs):
    return max(c.depth_value(x) for x in xs)
