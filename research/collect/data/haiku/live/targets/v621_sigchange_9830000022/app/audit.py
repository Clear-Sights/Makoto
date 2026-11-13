from app import core as c

def audit_max(xs):
    return max(c.weight(x)["value"] for x in xs)
