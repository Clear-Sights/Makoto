from app.core import length, length_value

def test_length():
    assert length(2) == {"value": 8, "unit": "m"}

def test_length_value():
    assert length_value(2) == 8
