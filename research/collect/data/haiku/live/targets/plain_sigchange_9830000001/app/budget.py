from app import core
OPS = {'main': lambda x: core.price(x)["value"]}

def budget_run(x):
    return OPS['main'](x) * 2
