"""Row rendering step 1."""

from app.index import show_item


def render_row(x):
    return show_item(x) + ';'
