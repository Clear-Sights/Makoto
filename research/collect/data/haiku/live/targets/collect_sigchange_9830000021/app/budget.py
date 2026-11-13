from app.core import credit

def budget_apply(x, f=lambda x: credit(x)["value"]):
    return f(x) - 6
