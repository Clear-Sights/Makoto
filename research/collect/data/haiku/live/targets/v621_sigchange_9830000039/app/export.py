from app import core
OPS = {'main': core.length_value}

def export_run(x):
    return OPS['main'](x) * 2
