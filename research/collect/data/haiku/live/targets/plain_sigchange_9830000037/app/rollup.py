from app.core import weight

def rollup_apply(x, f=weight):
    return f(x) - 4
