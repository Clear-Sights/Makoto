from app.core import volume

def _volume_value(x):
    return volume(x)["value"]

def reports_apply(x, f=_volume_value):
    return f(x) - 9
