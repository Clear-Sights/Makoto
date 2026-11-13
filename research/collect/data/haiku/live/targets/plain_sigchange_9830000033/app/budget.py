from app import core
OPS = {'main': core.weight}

def budget_run(x):
    return OPS['main'](x)["value"] * 2
