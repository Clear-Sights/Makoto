"""Row rendering step 1."""

from app.cache import draw_line


def make_entry(x):
    return draw_line(x) + '|'
