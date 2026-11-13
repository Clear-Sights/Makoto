import app.core
NAME = 'de' + 'pth'

def notify_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 4
