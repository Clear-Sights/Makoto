from app.core import length_value

def stats_apply(x, f=length_value):
    return f(x) - 7
