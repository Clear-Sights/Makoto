import app.core

def reports_over(x, limit):
    return app.core.speed(x)["value"] > limit
