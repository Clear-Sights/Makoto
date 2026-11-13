"""Row rendering step 1."""

from app.report import format_cell


def draw_line(x):
    return format_cell(x) + '>'
