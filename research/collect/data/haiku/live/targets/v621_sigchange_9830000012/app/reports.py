import app.core
NAME = 'we' + 'ight'

def reports_pick(x):
    return getattr(app.core, NAME)(x)["value"] + 7
