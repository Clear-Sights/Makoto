import app.core

def budget_over(x, limit):
    return app.core.depth(x)["value"] > limit
