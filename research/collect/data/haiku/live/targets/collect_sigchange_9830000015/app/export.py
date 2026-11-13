from app.core import score as measure

def export_scaled(x):
    return measure(x)["value"] * 2
