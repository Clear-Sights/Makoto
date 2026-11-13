from app.core import weight

def _weight_value(x):
    return weight(x)["value"]

def audit_apply(x, f=_weight_value):
    return f(x) - 4
