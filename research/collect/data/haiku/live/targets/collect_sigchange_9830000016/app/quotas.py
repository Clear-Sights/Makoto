import app.core
NAME = 'de' + 'pth'

def quotas_pick(x):
    return getattr(app.core, NAME)(x) + 7
