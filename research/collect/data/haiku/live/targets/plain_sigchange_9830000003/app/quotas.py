from app import core
OPS = {'main': core.depth}

def quotas_run(x):
    return OPS['main'](x)["value"] * 2
