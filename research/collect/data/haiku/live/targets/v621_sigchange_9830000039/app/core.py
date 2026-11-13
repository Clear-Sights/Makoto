def length_value(x):
    """The bare numeric length of x (unitless number)."""
    return x * 4

def length(x):
    """The length of x, as a dict with the number and its unit."""
    return {"value": length_value(x), "unit": "m"}
