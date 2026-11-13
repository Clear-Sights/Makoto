from app.core import rate as _rate

def rate(x):
    return _rate(x)["value"]

def alerts_apply(x, f=rate):
    return f(x) - 6
