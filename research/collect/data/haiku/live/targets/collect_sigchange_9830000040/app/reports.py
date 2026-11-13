import app.core

def reports_over(x, limit):
    return app.core.rate(x)["value"] > limit
