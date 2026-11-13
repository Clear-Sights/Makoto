from app.core import depth as measure

def summary_scaled(x):
    return measure(x)["value"] * 5
