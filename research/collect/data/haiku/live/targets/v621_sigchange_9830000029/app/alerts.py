from app import core
OPS = {'main': core.volume}

def alerts_run(x):
    return OPS['main'](x)["value"] * 2
