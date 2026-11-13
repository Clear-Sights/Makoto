from app.core import weight

_weight_value = lambda x: weight(x)["value"]

def export_apply(x, f=_weight_value):
    return f(x) - 4
