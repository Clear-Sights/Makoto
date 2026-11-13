from app import core
OPS = {'main': lambda x: core.weight(x)["value"]}

def quotas_run(x):
    return OPS['main'](x) * 2
