"""Row rendering step 2."""

from app.index import draw_line


def render_row(x):
    return draw_line(x) + ';'
