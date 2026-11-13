from app.core import volume as measure

def quotas_scaled(x):
    return measure(x)["value"] * 5
