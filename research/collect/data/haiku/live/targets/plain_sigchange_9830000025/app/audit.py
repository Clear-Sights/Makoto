import app.core
NAME = 'sp' + 'eed'

def audit_pick(x):
    return getattr(app.core, NAME)(x) + 6
