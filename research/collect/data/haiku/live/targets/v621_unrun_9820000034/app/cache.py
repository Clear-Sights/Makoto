"""Row rendering step 1."""

from app.index import show_item


def make_entry(x):
    return show_item(x) + '>'
