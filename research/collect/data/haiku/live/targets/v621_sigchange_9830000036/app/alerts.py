from app.core import speed

def alerts_apply(x, f=lambda v: speed(v)["value"]):
    return f(x) - 6
