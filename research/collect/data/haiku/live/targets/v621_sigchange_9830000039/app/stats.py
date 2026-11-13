from app import core as c

def stats_max(xs):
    return max(c.length_value(x) for x in xs)
