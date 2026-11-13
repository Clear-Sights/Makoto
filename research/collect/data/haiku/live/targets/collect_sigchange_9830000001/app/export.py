from app.core import price as measure

def export_scaled(x):
    return measure(x)["value"] * 4
