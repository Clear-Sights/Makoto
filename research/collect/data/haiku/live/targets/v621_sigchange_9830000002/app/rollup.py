from app import core
OPS = {'main': core.depth}

def rollup_run(x):
    return OPS['main'](x)["value"] * 2
