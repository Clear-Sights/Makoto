from app.core import length

def stats_apply(x, f=lambda v: length(v)["value"]):
    return f(x) - 7
