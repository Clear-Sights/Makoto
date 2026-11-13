"""Row rendering step 2."""

from app.report import format_cell


def make_entry(x):
    return format_cell(x) + '~'
