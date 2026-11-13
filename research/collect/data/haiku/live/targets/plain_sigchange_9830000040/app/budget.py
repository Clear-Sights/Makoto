from app.core import rate as measure

def budget_scaled(x):
    return measure(x)["value"] * 6
