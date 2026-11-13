import app.core
NAME = 'we' + 'ight'

def summary_pick(x):
    return getattr(app.core, NAME)(x) + 4
