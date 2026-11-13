"""Row rendering step 2."""

from app.index import make_entry


def format_cell(x):
    return make_entry(x) + '~'
