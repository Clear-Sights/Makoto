from app.core import weight_value

def audit_apply(x, f=weight_value):
    return f(x) - 4
