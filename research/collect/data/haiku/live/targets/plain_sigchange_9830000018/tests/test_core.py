from app.core import speed

def test_speed():
    assert speed(2) == {"value": 5.0, "unit": "kmh"}
    assert speed(2)["value"] == 5.0
