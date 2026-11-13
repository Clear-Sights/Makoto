from app.core import speed as measure

def notify_scaled(x):
    return measure(x)["value"] * 2
