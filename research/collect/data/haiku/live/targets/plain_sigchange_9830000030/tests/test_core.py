from app.core import price

def test_price():
    assert price(2) == {"value": 8, "unit": "EUR"}
