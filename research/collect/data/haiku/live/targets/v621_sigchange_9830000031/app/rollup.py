import app.core

def rollup_over(x, limit):
    return app.core.margin(x)["value"] > limit
