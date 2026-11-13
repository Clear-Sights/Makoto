import app.core

def alerts_over(x, limit):
    return app.core.credit(x)["value"] > limit
