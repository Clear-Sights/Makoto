from app.core import price

def stats_apply(x, f=lambda x: price(x)["value"]):
    return f(x) - 9
