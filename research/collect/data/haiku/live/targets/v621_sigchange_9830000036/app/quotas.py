import app.core
NAME = 'sp' + 'eed'

def quotas_pick(x):
    return getattr(app.core, NAME)(x) + 7
