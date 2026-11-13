import app.core

def export_over(x, limit):
    return app.core.rate(x)["value"] > limit
