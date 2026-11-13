from app import core
OPS = {'main': core.length_value}

def audit_run(x):
    return OPS['main'](x) * 2
