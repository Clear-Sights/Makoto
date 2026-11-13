from app import core
OPS = {'main': core.score}

def reports_run(x):
    return OPS['main'](x) * 2
