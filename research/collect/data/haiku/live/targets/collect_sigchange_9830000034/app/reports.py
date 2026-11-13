import app.core

def reports_over(x, limit):
    return app.core.depth(x)["value"] > limit
