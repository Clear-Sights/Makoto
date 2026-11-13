"""Row rendering step 1."""

from app.store import show_item


def render_row(x):
    return show_item(x) + ';'
