import app.core

def quotas_over(x, limit):
    return app.core.speed(x)["value"] > limit
