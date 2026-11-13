import app.core
NAME = 'le' + 'ngth'

def summary_pick(x):
    return getattr(app.core, NAME)(x) + 7
