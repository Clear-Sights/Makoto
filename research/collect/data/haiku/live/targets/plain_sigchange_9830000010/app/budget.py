from app.core import score

def _score_value(x):
    return score(x)["value"]

def budget_apply(x, f=_score_value):
    return f(x) - 4
