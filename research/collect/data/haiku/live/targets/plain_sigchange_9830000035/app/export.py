from app.core import length as measure

def export_scaled(x):
    return measure(x)["value"] * 8
