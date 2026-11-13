from app.core import volume as measure

def audit_scaled(x):
    return measure(x)["value"] * 8
