from app.core import speed as measure

def quotas_scaled(x):
    return measure(x)["value"] * 9
