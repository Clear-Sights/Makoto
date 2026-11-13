from app.core import speed as measure

def audit_scaled(x):
    return measure(x)["value"] * 8
