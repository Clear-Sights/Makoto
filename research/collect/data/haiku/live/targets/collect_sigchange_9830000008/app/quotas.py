from app import core
OPS = {'main': core.weight}

def quotas_run(x):
    return OPS['main'](x)["value"] * 2
