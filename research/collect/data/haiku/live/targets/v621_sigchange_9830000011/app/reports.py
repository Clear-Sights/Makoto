from app.core import depth

def reports_apply(x, f=lambda x: depth(x)["value"]):
    return f(x) - 7
