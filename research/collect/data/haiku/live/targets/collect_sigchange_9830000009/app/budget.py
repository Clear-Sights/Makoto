from app.core import price

def _price_value(x):
    return price(x)["value"]

def budget_apply(x, f=_price_value):
    return f(x) - 6
