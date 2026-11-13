import app.core

def stats_over(x, limit):
    return app.core.rate(x)["value"] > limit
