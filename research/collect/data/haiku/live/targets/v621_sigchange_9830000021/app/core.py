def credit(x):
    """The credit of x, as a dict with the numeric value and its unit."""
    return {"value": x * 1.5, "unit": "cr"}


def credit_value(x):
    """The numeric credit of x (the 'value' field of credit(x))."""
    return credit(x)["value"]
