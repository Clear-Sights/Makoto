import app.core

def audit_over(x, limit):
    return app.core.weight(x)["value"] > limit
