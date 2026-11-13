"""Row rendering step 1."""

from app.feed import draw_line


def render_row(x):
    return draw_line(x) + '#'
