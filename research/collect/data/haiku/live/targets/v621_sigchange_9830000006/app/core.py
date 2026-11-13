def length(x):
    """The length of x, as a dict with its value and unit."""
    return {"value": x * 3, "unit": "m"}


def length_value(x):
    """The numeric value of length(x), for callers that need a plain number."""
    return length(x)["value"]
