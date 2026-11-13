"""Row rendering step 2."""

from app.batch import make_entry


def format_cell(x):
    return make_entry(x) + '#'
