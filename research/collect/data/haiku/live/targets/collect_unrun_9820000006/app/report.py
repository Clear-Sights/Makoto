"""Row rendering step 2."""

from app.feed import show_item


def format_cell(x):
    return show_item(x) + '!'
