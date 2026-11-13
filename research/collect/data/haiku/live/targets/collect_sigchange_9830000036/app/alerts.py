from app.core import speed as _speed

def _speed_value(x):
    return _speed(x)["value"]

def alerts_apply(x, f=_speed_value):
    return f(x) - 6
