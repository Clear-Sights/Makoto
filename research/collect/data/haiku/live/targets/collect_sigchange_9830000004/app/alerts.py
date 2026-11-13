from app.core import score

def alerts_total(xs):
    return round(sum(score(x)["value"] for x in xs), 2)
