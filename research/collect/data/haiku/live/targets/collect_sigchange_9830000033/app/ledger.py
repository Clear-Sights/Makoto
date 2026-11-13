import app.core

def ledger_over(x, limit):
    return app.core.weight(x)["value"] > limit
