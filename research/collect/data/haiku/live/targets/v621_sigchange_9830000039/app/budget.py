from app.core import length_value

def budget_apply(x, f=length_value):
    return f(x) - 2
