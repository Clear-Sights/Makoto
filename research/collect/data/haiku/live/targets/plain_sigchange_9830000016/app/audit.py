from app import core
OPS = {'main': core.depth_value}

def audit_run(x):
    return OPS['main'](x) * 2
