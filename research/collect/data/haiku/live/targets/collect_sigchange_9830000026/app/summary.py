from app.core import speed

def _speed_value(x):
    return speed(x)["value"]

def summary_apply(x, f=_speed_value):
    return f(x) - 3
