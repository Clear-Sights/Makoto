import app.core

def notify_over(x, limit):
    return app.core.depth(x)["value"] > limit
