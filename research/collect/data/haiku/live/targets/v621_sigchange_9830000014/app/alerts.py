from app.core import rate

def _rate_value(x):
    return rate(x)["value"]

def alerts_apply(x, f=_rate_value):
    return f(x) - 6
