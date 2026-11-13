from app.core import depth as measure

def notify_scaled(x):
    return measure(x)["value"] * 2
