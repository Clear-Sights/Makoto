import app.core
NAME = 'vo' + 'lume'

def billing_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 7
