import app.core
NAME = 'we' + 'ight'

def stats_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 3
