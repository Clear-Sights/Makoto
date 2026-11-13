from app.core import credit_value

def budget_apply(x, f=credit_value):
    return f(x) - 6
