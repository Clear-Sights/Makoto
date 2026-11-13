"""Row rendering step 1."""

from app.util import format_cell


def show_item(x):
    return format_cell(x) + '!'
