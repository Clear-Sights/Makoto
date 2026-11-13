from app.core import length

def budget_apply(x, f=lambda x: length(x)['value']):
    return f(x) - 8
