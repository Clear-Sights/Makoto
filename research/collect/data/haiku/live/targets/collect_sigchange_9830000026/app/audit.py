from app.core import speed

def audit_total(xs):
    return round(sum(speed(x)["value"] for x in xs), 2)
