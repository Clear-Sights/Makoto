import app.core

def budget_over(x, limit):
    return app.core.volume(x)['value'] > limit
