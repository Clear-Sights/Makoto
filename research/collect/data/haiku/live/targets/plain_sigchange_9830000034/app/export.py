import app.core

def export_over(x, limit):
    return app.core.depth(x)["value"] > limit
