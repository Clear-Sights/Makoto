from app.core import speed

def export_total(xs):
    return round(sum(speed(x)["value"] for x in xs), 2)
