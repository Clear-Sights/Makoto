from app import core
OPS = {'main': core.speed}

def alerts_run(x):
    return OPS['main'](x)["value"] * 2
