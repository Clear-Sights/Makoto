from app.core import price

def budget_apply(x, f=lambda x: price(x)["value"]):
    return f(x) - 6
