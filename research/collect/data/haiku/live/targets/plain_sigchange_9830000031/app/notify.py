from app import core
OPS = {'main': core.margin}

def notify_run(x):
    return OPS['main'](x)["value"] * 2
