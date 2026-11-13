from app.core import rate

def test_rate():
    assert rate(2) == {"value": 8, "unit": "pct"}
