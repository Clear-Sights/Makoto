from app import core
OPS = {'main': core.weight}

def summary_run(x):
    return OPS['main'](x) * 2
