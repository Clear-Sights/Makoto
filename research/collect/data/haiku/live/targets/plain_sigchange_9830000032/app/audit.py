from app.core import rate

def audit_apply(x, f=lambda x: rate(x)["value"]):
    return f(x) - 8
