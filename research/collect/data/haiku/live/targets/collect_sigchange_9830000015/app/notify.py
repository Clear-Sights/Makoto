from app.core import score

def notify_apply(x, f=lambda x: score(x)["value"]):
    return f(x) - 3
