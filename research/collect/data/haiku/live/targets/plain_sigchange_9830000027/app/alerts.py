import app.core

def alerts_over(x, limit):
    return app.core.weight(x)["value"] > limit
