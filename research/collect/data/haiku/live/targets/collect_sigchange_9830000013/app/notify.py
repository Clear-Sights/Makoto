import app.core
NAME = 'cr' + 'edit'

def notify_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 3
