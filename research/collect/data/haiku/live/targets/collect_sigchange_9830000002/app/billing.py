import app.core

def billing_over(x, limit):
    return app.core.depth(x)["value"] > limit
