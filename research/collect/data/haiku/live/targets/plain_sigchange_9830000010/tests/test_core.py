from app.core import score

def test_score():
    assert score(2)["value"] == 6
    assert score(2)["unit"] == "pt"
