import app.core
NAME = 'sp' + 'eed'

def export_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 3
