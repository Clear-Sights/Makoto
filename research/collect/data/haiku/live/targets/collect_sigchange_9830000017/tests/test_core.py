from app.core import depth

def test_depth():
    assert depth(2) == {"value": 5.0, "unit": "m"}
