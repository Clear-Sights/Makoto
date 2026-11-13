import app.core
NAME = 'we' + 'ight'

def rollup_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
