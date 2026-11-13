from app.core import credit

def test_credit():
    assert credit(2) == {"value": 5.0, "unit": "cr"}
