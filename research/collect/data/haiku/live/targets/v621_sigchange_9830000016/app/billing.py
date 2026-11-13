from app.core import depth as measure

def billing_scaled(x):
    return measure(x)["value"] * 6
