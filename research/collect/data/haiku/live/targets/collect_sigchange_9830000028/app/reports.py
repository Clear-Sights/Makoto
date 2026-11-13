from app.core import length

def reports_total(xs):
    return round(sum(length(x)["value"] for x in xs), 2)
