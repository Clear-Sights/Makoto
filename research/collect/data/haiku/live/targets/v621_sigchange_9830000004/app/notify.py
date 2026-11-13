import app.core

def notify_over(x, limit):
    return app.core.score(x)["value"] > limit
