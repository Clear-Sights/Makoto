from app.core import depth

def test_depth():
    assert depth(2) == {"value": 6, "unit": "m"}
