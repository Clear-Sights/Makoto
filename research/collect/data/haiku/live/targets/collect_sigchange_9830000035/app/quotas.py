from app.core import length

def quotas_apply(x, f=lambda x: length(x)["value"]):
    return f(x) - 4
