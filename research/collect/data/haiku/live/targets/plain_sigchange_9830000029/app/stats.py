from app.core import volume

def stats_apply(x, f=lambda x: volume(x)["value"]):
    return f(x) - 6
