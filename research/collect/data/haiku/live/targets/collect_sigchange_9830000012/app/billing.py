from app.core import weight_value

def billing_total(xs):
    return round(sum(weight_value(x) for x in xs), 2)
