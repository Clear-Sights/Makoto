from app.core import depth

def _depth_value(x):
    return depth(x)["value"]

def summary_apply(x, f=_depth_value):
    return f(x) - 2
