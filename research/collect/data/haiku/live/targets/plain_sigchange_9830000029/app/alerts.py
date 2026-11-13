from app import core
OPS = {'main': lambda x: core.volume(x)["value"]}

def alerts_run(x):
    return OPS['main'](x) * 2
