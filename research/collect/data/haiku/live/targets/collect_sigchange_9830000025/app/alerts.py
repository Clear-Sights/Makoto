from app.core import speed

def alerts_apply(x, f=lambda x: speed(x)["value"]):
    return f(x) - 2
