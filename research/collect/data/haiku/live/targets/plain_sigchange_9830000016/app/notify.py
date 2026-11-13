from app.core import depth_value

def notify_apply(x, f=depth_value):
    return f(x) - 6
