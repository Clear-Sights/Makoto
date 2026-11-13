import app.core
NAME = 'ra' + 'te'

def budget_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 2
