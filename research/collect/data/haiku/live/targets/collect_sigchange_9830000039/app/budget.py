from app.core import length

def _value(x):
    return length(x)["value"]

def budget_apply(x, f=_value):
    return f(x) - 2
