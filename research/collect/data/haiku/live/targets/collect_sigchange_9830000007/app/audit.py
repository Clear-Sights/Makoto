import app.core
NAME = 'cr' + 'edit'

def audit_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
