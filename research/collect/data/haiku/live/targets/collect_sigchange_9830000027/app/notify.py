import app.core
NAME = 'we' + 'ight'

def notify_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 5
