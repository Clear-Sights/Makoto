from app.core import weight

def test_weight():
    assert weight(2) == {"value": 8, "unit": "kg"}
