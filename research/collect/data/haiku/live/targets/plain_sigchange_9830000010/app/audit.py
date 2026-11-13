from app.core import score as measure

def audit_scaled(x):
    return measure(x)["value"] * 2
