from app.core import depth as measure

def stats_scaled(x):
    return measure(x)["value"] * 6
