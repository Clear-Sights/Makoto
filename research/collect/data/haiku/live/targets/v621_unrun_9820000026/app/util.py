"""Row rendering step 1."""

from app.cache import format_cell


def make_entry(x):
    return format_cell(x) + '|'
