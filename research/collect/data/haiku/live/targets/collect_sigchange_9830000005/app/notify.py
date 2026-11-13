import app.core

def notify_over(x, limit):
    return app.core.speed(x)["value"] > limit
