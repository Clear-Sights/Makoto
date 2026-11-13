from app.core import volume

def budget_total(xs):
    return round(sum(volume(x)["value"] for x in xs), 2)
