import app.core

def alerts_over(x, limit):
    return app.core.price(x)["value"] > limit
