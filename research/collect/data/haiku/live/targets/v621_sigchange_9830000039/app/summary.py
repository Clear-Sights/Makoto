from app.core import length_value

def summary_total(xs):
    return round(sum(length_value(x) for x in xs), 2)
