from app import core
OPS = {'main': core.rate}

def billing_run(x):
    return OPS['main'](x)["value"] * 2
