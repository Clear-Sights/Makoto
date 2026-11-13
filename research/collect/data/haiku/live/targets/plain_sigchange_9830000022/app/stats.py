from app.core import weight

def stats_apply(x, f=weight):
    return f(x) - 9
