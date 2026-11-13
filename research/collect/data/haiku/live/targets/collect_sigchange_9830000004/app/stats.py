from app.core import score as measure

def stats_scaled(x):
    return measure(x)["value"] * 2
