import app.core
NAME = 'sp' + 'eed'

def audit_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 6
