import app.core

def budget_over(x, limit):
    return app.core.rate(x)["value"] > limit
