from app.core import depth as measure

def budget_scaled(x):
    return measure(x)["value"] * 6
