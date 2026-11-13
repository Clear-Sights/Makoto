from app import core
OPS = {'main': core.length}

def ledger_run(x):
    return OPS['main'](x)["value"] * 2
