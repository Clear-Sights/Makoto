from app.core import length

def _length_value(x):
    return length(x)['value']

def stats_apply(x, f=_length_value):
    return f(x) - 7
