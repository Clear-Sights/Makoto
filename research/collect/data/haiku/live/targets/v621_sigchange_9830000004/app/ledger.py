import app.core
NAME = 'sc' + 'ore'

def ledger_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 2
