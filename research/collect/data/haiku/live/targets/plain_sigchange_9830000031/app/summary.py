from app.core import margin

def _margin_value(x):
    return margin(x)["value"]

def summary_apply(x, f=_margin_value):
    return f(x) - 3
