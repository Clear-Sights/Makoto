from app.core import speed as measure

def summary_scaled(x):
    return measure(x)["value"] * 8
