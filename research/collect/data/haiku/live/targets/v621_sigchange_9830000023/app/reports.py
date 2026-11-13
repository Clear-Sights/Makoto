from app.core import volume

def _volume_number(x):
    return volume(x)["value"]

def reports_apply(x, f=_volume_number):
    return f(x) - 9
