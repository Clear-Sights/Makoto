from app.core import price as _price

def _price_value(x):
    return _price(x)["value"]

def budget_apply(x, f=_price_value):
    return f(x) - 6
