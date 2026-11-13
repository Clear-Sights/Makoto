import app.core

def stats_over(x, limit):
    return app.core.price(x)["value"] > limit
