from app.core import speed as measure

def stats_scaled(x):
    return measure(x)["value"] * 3
