import app.core

def ledger_over(x, limit):
    return app.core.depth(x)["value"] > limit
