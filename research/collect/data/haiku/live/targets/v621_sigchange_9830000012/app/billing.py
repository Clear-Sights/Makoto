from app.core import weight

def billing_total(xs):
    return round(sum(weight(x)["value"] for x in xs), 2)
