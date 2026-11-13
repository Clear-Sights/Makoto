from app import core
OPS = {'main': core.score}

def ledger_run(x):
    return OPS['main'](x)["value"] * 2
