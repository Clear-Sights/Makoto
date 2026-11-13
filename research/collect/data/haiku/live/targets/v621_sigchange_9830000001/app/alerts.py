from app.core import price as measure

def alerts_scaled(x):
    return measure(x)["value"] * 2
