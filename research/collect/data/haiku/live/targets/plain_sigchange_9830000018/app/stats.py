import app.core

def stats_over(x, limit):
    return app.core.speed(x)["value"] > limit
