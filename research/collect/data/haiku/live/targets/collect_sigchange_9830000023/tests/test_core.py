from app.core import volume

def test_volume():
    assert volume(2) == {"value": 6, "unit": "l"}
    assert volume(2)["value"] == 6
