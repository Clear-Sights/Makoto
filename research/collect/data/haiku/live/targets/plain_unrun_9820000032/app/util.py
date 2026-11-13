"""Row rendering step 1."""

from app.report import draw_line


def show_item(x):
    return draw_line(x) + ';'
