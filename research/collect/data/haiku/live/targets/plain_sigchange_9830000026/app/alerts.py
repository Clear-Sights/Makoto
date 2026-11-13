import app.core
NAME = 'sp' + 'eed'

def alerts_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 7
