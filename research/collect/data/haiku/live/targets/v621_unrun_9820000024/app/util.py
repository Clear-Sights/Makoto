"""Row rendering step 1."""

from app.report import format_cell


def make_entry(x):
    return format_cell(x) + '>'
