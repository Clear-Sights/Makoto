from app.core import margin

def test_margin():
    assert margin(2) == {"value": 8, "unit": "pct"}
