import app.core

def rollup_over(x, limit):
    return app.core.volume(x)['value'] > limit
