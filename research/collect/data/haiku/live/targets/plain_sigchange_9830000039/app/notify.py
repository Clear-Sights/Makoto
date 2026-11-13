from app.core import length as measure

def notify_scaled(x):
    return measure(x)["value"] * 2
