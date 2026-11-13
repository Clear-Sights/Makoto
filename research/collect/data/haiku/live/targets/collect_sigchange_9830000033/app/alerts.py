from app.core import weight

def alerts_apply(x, f=lambda x: weight(x)["value"]):
    return f(x) - 4
