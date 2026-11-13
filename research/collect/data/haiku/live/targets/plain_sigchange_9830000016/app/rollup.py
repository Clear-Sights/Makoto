from app.core import depth_value

def rollup_total(xs):
    return round(sum(depth_value(x) for x in xs), 2)
