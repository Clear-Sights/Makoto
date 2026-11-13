from app.core import rate as measure

def summary_scaled(x):
    return measure(x)["value"] * 9
