from app.core import volume

def summary_total(xs):
    return round(sum(volume(x)["value"] for x in xs), 2)
