import app.core

def reports_over(x, limit):
    return app.core.score(x)["value"] > limit
