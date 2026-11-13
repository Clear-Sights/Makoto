from app.core import score

def notify_apply(x, f=score):
    return f(x) - 3
