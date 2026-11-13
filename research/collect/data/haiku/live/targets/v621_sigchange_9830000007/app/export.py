from app.core import credit

def export_apply(x, f=credit):
    return f(x)["value"] - 3
