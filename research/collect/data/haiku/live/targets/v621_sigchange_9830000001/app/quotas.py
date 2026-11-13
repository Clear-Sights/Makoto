import app.core

def quotas_over(x, limit):
    return app.core.price(x)["value"] > limit
