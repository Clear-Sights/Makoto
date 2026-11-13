"""Row rendering step 1."""

from app.index import make_entry


def format_cell(x):
    return make_entry(x) + ';'
