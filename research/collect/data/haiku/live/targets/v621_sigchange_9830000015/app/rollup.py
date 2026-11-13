import app.core

def rollup_over(x, limit):
    return app.core.score(x)["value"] > limit
