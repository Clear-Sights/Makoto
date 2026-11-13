from app.core import volume

def _volume_value(x):
    return volume(x)["value"]

def stats_apply(x, f=_volume_value):
    return f(x) - 6
