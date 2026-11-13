from app.core import price

def summary_total(xs):
    return round(sum(price(x)["value"] for x in xs), 2)
