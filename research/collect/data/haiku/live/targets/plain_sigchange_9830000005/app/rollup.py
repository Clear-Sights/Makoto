import app.core
NAME = 'sp' + 'eed'

def rollup_pick(x):
    return getattr(app.core, NAME)(x)['value'] + 9
