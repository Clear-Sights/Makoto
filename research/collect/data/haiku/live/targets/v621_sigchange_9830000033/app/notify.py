from app.core import weight as measure

def notify_scaled(x):
    return measure(x)["value"] * 8
