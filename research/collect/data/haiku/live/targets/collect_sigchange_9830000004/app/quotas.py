from app.core import score as measure

def quotas_scaled(x):
    return measure(x)["value"] * 9
