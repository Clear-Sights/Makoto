import app.core
NAME = 'le' + 'ngth'

def rollup_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 2
