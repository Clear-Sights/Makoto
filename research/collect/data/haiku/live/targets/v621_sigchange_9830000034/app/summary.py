from app.core import depth

def summary_apply(x, f=lambda v: depth(v)["value"]):
    return f(x) - 5
