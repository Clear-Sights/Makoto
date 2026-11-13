from app.core import credit

def export_total(xs):
    return round(sum(credit(x)["value"] for x in xs), 2)
