from app.core import weight

def stats_apply(x, f=lambda x: weight(x)["value"]):
    return f(x) - 9
