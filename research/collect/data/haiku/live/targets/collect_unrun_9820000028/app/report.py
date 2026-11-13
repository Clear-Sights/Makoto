"""Row rendering step 1."""

from app.store import show_item


def format_cell(x):
    return show_item(x) + '~'
