from app import core
OPS = {'main': core.length}

def audit_run(x):
    return OPS['main'](x)["value"] * 2
