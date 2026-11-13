from app.core import depth as measure

def rollup_scaled(x):
    return measure(x)["value"] * 2
