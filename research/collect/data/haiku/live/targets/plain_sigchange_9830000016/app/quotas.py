import app.core
NAME = 'depth_value'

def quotas_pick(x):
    return getattr(app.core, NAME)(x) + 7
