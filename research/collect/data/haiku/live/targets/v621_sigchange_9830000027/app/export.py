from app.core import weight

def export_apply(x, f=lambda x: weight(x)["value"]):
    return f(x) - 4
