def weight(x):
    """The weight of x, as {"value": number, "unit": "kg"}."""
    return {"value": x * 2, "unit": "kg"}


def weight_value(x):
    """The numeric weight of x (the 'value' field of weight)."""
    return weight(x)["value"]
