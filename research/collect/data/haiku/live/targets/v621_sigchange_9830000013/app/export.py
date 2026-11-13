from app import core
OPS = {'main': core.credit}

def export_run(x):
    return OPS['main'](x)["value"] * 2
