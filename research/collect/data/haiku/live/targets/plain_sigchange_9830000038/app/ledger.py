import app.core
NAME = 'sp' + 'eed'

def ledger_pick(x):
    return getattr(app.core, NAME)(x) + 4
