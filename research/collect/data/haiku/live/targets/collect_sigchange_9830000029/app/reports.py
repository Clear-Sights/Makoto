from app import core as c

def reports_max(xs):
    return max(c.volume(x)['value'] for x in xs)
