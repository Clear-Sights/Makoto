"""Row rendering step 1."""

from app.feed import format_cell


def draw_line(x):
    return format_cell(x) + '~'
