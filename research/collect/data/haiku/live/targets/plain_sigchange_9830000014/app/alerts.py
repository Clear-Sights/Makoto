from app.core import rate

def alerts_apply(x, f=lambda v: rate(v)["value"]):
    return f(x) - 6
