import pytest


@pytest.fixture(autouse=True)
def _no_block_in(monkeypatch):
    """The scope setting lives in the developer's settings; tests choose their own."""
    monkeypatch.delenv('MAKOTO_BLOCK_IN', raising=False)
