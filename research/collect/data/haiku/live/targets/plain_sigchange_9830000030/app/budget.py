from app.core import price

def budget_apply(x, f=price):
    return f(x) - 6
