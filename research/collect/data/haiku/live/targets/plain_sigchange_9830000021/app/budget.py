from app.core import credit as _credit

def _credit_value(x):
    return _credit(x)["value"]

def budget_apply(x, f=_credit_value):
    return f(x) - 6
