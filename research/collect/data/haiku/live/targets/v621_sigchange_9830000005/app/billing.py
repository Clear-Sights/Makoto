from app.core import speed

def billing_apply(x, f=lambda x: speed(x)["value"]):
    return f(x) - 2
