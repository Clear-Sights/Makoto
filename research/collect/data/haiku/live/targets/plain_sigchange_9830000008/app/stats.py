from app.core import weight as measure

def stats_scaled(x):
    return measure(x)["value"] * 9
