from app.core import credit

def summary_total(xs):
    return round(sum(credit(x)["value"] for x in xs), 2)
