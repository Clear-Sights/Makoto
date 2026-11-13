from app.core import weight as measure

def rollup_scaled(x):
    return measure(x)["value"] * 2
