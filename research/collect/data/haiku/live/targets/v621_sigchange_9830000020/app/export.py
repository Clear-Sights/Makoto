from app.core import margin

def export_apply(x, f=lambda x: margin(x)["value"]):
    return f(x) - 4
