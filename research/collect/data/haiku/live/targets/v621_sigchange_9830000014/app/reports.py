import app.core
NAME = 'ra' + 'te'

def reports_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 3
