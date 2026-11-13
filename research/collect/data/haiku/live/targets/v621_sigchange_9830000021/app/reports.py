from app import core
OPS = {'main': core.credit_value}

def reports_run(x):
    return OPS['main'](x) * 2
