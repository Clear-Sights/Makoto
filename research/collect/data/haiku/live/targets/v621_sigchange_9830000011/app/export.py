from app import core
OPS = {'main': core.depth}

def export_run(x):
    return OPS['main'](x)["value"] * 2
