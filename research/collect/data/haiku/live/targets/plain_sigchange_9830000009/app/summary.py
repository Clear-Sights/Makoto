import app.core
NAME = 'pr' + 'ice'

def summary_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
