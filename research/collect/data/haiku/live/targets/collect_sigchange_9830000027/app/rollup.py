from app import core

def _weight_value(x):
    return core.weight(x)["value"]

OPS = {'main': _weight_value}

def rollup_run(x):
    return OPS['main'](x) * 2
