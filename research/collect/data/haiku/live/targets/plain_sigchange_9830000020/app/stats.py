import app.core
NAME = 'ma' + 'rgin'

def stats_pick(x):
    return getattr(app.core, NAME)(x) + 3
