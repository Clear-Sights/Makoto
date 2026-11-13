import app.core
NAME = 'de' + 'pth'

def ledger_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
