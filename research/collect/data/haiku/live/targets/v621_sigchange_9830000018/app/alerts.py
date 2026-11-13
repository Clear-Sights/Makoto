from app.core import speed as measure

def alerts_scaled(x):
    return measure(x)['value'] * 9
