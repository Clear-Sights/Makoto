from app.core import volume as measure

def billing_scaled(x):
    return measure(x)["value"] * 6
