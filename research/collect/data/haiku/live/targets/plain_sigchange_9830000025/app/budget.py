from app import core
OPS = {'main': core.speed}

def budget_run(x):
    return OPS['main'](x) * 2
