"""Row rendering step 2."""

from app.batch import format_cell


def render_row(x):
    return format_cell(x) + ';'
