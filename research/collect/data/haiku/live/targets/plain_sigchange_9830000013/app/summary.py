from app.core import credit

def summary_apply(x, f=lambda v: credit(v)["value"]):
    return f(x) - 6
