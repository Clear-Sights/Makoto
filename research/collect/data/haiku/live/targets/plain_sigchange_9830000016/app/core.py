def depth_value(x):
    """The depth of x, as a number."""
    return x * 2

def depth(x):
    """The depth of x, as a dict with its value and unit."""
    return {"value": depth_value(x), "unit": "m"}
