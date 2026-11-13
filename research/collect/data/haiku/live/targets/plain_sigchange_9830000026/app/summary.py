from app.core import speed

def summary_apply(x, f=lambda x: speed(x)["value"]):
    return f(x) - 3
