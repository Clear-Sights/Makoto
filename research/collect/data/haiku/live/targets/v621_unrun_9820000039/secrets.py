"""Root helper for the `secrets` topic.

This file shadows the standard library `secrets` module when the project root
is on sys.path. `app/batch.py` relies on `secrets.compare_digest`, so that name
is re-exported here (the stdlib `secrets` module imports it from `hmac` too).
"""
from hmac import compare_digest  # noqa: F401  (used by app/batch.py)


def total_squares(values):
    return sum(v * v for v in values)
