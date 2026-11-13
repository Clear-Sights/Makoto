import app.core

def audit_over(x, limit):
    return app.core.price(x)["value"] > limit
