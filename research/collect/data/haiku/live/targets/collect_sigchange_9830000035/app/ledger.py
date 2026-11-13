from app import core
OPS = {'main': lambda x: core.length(x)["value"]}

def ledger_run(x):
    return OPS['main'](x) * 2
