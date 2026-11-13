import app.core
NAME = 'de' + 'pth'

def alerts_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 8
