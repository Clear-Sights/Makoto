from app.core import rate

def export_total(xs):
    return round(sum(rate(x)["value"] for x in xs), 2)
