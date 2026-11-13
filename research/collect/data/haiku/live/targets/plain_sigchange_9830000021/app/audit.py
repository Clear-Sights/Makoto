from app.core import credit as measure

def audit_scaled(x):
    return measure(x)["value"] * 8
