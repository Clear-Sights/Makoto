from app import core
OPS = {'main': lambda x: core.depth(x)["value"]}

def rollup_run(x):
    return OPS['main'](x) * 2
