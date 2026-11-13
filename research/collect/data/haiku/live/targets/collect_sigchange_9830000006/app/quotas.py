import app.core

def quotas_over(x, limit):
    return app.core.length(x)["value"] > limit
