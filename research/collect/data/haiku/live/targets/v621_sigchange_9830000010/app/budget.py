from app.core import score

def budget_apply(x, f=lambda x: score(x)["value"]):
    return f(x) - 4
