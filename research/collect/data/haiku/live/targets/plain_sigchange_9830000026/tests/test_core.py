from app.core import speed

def test_speed():
    assert speed(2) == {"value": 4, "unit": "kmh"}
