from app.core import weight as measure

def quotas_scaled(x):
    return measure(x)["value"] * 7
