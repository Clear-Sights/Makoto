from app.core import score as _score

def score(x):
    return _score(x)["value"]

def summary_apply(x, f=score):
    return f(x) - 5
