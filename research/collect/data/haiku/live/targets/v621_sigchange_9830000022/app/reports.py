import app.core

def reports_over(x, limit):
    return app.core.weight(x)["value"] > limit
