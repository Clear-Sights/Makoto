from app import core
OPS = {'main': core.weight}

def stats_run(x):
    return OPS['main'](x) * 2
