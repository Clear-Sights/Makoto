from app.core import credit

def test_credit():
    assert credit(2) == {"value": 4, "unit": "cr"}
