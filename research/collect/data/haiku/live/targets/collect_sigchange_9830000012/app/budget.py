from app import core
OPS = {'main': core.weight_value}

def budget_run(x):
    return OPS['main'](x) * 2
