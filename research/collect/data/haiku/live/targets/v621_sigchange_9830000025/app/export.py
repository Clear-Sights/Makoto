from app.core import speed as measure

def export_scaled(x):
    return measure(x)["value"] * 8
