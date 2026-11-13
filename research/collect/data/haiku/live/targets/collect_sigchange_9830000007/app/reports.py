from app import core
OPS = {'main': core.credit}

def reports_run(x):
    return OPS['main'](x)["value"] * 2
