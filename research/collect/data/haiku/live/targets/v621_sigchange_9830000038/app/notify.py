from app.core import speed

def _speed_value(x):
    return speed(x)["value"]

def notify_apply(x, f=_speed_value):
    return f(x) - 2
