from app.core import credit, credit_value

def test_credit():
    assert credit(2) == {"value": 3.0, "unit": "cr"}

def test_credit_value():
    assert credit_value(2) == 3.0
