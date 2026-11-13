import app.core
NAME = 'pr' + 'ice'

def audit_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
