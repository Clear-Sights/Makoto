import app.core

def ledger_over(x, limit):
    return app.core.volume(x)["value"] > limit
