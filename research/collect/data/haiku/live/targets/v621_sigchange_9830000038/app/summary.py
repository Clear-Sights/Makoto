from app.core import speed

def summary_total(xs):
    return round(sum(speed(x)["value"] for x in xs), 2)
