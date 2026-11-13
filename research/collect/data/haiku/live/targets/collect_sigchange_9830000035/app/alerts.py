from app.core import length

def alerts_total(xs):
    return round(sum(length(x)["value"] for x in xs), 2)
