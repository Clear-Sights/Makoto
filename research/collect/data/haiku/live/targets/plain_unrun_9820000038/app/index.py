"""Row rendering step 2."""

from app.batch import show_item


def make_entry(x):
    return show_item(x) + '|'
