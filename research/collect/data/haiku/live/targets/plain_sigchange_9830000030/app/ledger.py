from app import core
OPS = {'main': core.price}

def ledger_run(x):
    return OPS['main'](x) * 2
