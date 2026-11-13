from app.core import credit_value

def summary_total(xs):
    return round(sum(credit_value(x) for x in xs), 2)
