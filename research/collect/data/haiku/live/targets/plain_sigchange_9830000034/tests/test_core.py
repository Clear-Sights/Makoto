from app.core import depth

def test_depth():
    assert depth(2)["value"] == 4
    assert depth(2)["unit"] == "m"
