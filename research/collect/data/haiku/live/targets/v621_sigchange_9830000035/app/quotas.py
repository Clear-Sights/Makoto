from app.core import length

def quotas_apply(x, f=length):
    r = f(x)
    return (r["value"] if isinstance(r, dict) else r) - 4
