"""Row rendering step 2."""

from app.util import show_item


def make_entry(x):
    return show_item(x) + '!'
