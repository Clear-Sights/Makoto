from app.core import margin as measure

def budget_scaled(x):
    return measure(x)["value"] * 8
