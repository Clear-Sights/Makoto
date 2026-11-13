import app.core
NAME = 'sc' + 'ore'

def quotas_pick(x):
    return getattr(app.core, NAME)(x) + 7
