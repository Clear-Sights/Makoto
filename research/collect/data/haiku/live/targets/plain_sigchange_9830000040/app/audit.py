import app.core
NAME = 'ra' + 'te'

def audit_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 8
