from app.core import margin as _margin

def _margin_value(x):
    return _margin(x)["value"]

def export_apply(x, f=_margin_value):
    return f(x) - 4
