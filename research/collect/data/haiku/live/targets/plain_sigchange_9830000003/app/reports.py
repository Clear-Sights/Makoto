import app.core
NAME = 'de' + 'pth'

def reports_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 6
