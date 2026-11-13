from app.core import depth

def stats_apply(x, f=depth):
    return f(x)["value"] - 7
