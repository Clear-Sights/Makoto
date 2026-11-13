import app.core
NAME = 'le' + 'ngth'

def reports_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 3
