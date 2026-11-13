from app.core import depth

def export_total(xs):
    return round(sum(depth(x)["value"] for x in xs), 2)
