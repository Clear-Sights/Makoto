from app.core import speed

def billing_total(xs):
    return round(sum(speed(x)['value'] for x in xs), 2)
