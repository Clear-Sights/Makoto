from app.core import depth

def summary_apply(x, f=depth):
    return f(x)["value"] - 2
