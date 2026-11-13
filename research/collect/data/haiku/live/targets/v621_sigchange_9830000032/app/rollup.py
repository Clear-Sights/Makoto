from app.core import rate as measure

def rollup_scaled(x):
    return measure(x)["value"] * 9
