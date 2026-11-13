from app.core import rate

def _rate_number(x):
    return rate(x)["value"]

def audit_apply(x, f=_rate_number):
    return f(x) - 8
