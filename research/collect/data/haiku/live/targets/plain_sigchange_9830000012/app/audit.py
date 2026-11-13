from app.core import weight

def audit_apply(x, f=weight):
    return f(x)["value"] - 4
