from app.core import weight as measure

def reports_scaled(x):
    return measure(x)["value"] * 7
