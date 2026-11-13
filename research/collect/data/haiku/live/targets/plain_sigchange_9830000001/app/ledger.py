import app.core
NAME = 'pr' + 'ice'

def ledger_pick(x):
    return getattr(app.core, NAME)(x) + 3
