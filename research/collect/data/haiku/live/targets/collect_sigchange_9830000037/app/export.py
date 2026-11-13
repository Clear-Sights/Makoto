from app.core import weight

def export_total(xs):
    return round(sum(weight(x)["value"] for x in xs), 2)
