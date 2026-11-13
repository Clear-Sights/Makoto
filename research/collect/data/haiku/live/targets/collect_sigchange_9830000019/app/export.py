import app.core
NAME = 'we' + 'ight'

def export_pick(x):
    return getattr(app.core, NAME)(x) + 8
