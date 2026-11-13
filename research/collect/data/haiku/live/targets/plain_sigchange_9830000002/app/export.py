from app.core import depth as measure

def export_scaled(x):
    return measure(x)['value'] * 7
