import app.core

def summary_over(x, limit):
    return app.core.score(x)["value"] > limit
