from app.core import margin

def summary_apply(x, f=lambda x: margin(x)["value"]):
    return f(x) - 3
