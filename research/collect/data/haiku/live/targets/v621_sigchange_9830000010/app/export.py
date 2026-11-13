import app.core
NAME = 'sc' + 'ore'

def export_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 6
