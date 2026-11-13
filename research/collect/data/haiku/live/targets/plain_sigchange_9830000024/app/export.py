from app import core
OPS = {'main': lambda x: core.depth(x)["value"]}

def export_run(x):
    return OPS['main'](x) * 2
