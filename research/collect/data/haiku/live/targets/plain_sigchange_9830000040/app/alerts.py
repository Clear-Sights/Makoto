import app.core

def alerts_over(x, limit):
    return app.core.rate(x)["value"] > limit
