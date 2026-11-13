"""Row rendering step 2."""

from app.cache import draw_line


def format_cell(x):
    return draw_line(x) + ';'
