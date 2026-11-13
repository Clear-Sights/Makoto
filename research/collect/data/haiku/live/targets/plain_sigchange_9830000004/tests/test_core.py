from app.core import score

def test_score():
    assert score(2) == {"value": 5.0, "unit": "pt"}
