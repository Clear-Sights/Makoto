from app.core import weight, weight_value

def test_weight():
    assert weight(2) == {"value": 4, "unit": "kg"}
    assert weight_value(2) == 4
