from app.core import weight

def summary_total(xs):
    return round(sum(weight(x)["value"] for x in xs), 2)
