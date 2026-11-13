from app.core import margin as measure

def billing_scaled(x):
    return measure(x)["value"] * 4
