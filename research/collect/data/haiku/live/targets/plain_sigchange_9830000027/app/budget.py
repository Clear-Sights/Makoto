from app.core import weight

def budget_total(xs):
    return round(sum(weight(x)["value"] for x in xs), 2)
