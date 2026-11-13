from app import core as c

def notify_max(xs):
    return max(c.volume(x)["value"] for x in xs)
