import app.core

def rollup_over(x, limit):
    return app.core.weight(x)["value"] > limit
