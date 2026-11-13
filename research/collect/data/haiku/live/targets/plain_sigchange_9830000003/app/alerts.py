from app.core import depth as measure

def alerts_scaled(x):
    return measure(x)["value"] * 2
