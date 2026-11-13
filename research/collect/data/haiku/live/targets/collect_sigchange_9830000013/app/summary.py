from app.core import credit

def _credit_value(x):
    return credit(x)["value"]

def summary_apply(x, f=_credit_value):
    return f(x) - 6
