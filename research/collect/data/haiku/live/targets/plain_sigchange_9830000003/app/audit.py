import app.core

def audit_over(x, limit):
    return app.core.depth(x)["value"] > limit
