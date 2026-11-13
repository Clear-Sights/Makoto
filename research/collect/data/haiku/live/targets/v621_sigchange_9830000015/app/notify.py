from app.core import score

def _value(x):
    return score(x)["value"]

def notify_apply(x, f=_value):
    return f(x) - 3
