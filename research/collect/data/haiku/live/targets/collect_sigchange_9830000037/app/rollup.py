from app.core import weight

def rollup_apply(x, f=lambda v: weight(v)["value"]):
    return f(x) - 4
