from app.core import weight

def test_weight():
    assert weight(2)["value"] == 5.0
    assert weight(2)["unit"] == "kg"
