from app.core import weight

def billing_apply(x, f=lambda x: weight(x)["value"]):
    return f(x) - 6
