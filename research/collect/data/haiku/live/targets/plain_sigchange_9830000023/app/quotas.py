import app.core
NAME = 'vo' + 'lume'

def quotas_pick(x):
    return getattr(app.core, NAME)(x) + 3
