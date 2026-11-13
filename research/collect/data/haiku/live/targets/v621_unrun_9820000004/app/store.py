"""Row rendering step 2."""

from app.batch import format_cell


def show_item(x):
    return format_cell(x) + '#'
