import app.core
NAME = 'length_value'

def rollup_pick(x):
    return getattr(app.core, NAME)(x) + 2
