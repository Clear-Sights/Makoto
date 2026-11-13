from app.core import score as measure

def notify_scaled(x):
    return measure(x)["value"] * 7
