from app.core import depth

def summary_apply(x, f=lambda x: depth(x)["value"]):
    return f(x) - 2
