from app.core import credit_value as measure

def audit_scaled(x):
    return measure(x) * 8
