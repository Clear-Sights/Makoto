import app.core

def billing_over(x, limit):
    return app.core.weight(x)["value"] > limit
