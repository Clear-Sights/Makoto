from app.core import depth, depth_value

def test_depth():
    assert depth(2) == {"value": 4, "unit": "m"}

def test_depth_value():
    assert depth_value(2) == 4
