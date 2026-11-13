from app import core
OPS = {'main': lambda x: core.margin(x)["value"]}

def notify_run(x):
    return OPS['main'](x) * 2
