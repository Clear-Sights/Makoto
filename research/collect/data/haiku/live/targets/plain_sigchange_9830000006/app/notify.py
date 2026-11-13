import app.core
NAME = 'le' + 'ngth'

def notify_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 6
