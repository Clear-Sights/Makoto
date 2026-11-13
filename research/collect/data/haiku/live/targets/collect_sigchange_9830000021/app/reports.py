from app import core
OPS = {'main': lambda x: core.credit(x)["value"]}

def reports_run(x):
    return OPS['main'](x) * 2
