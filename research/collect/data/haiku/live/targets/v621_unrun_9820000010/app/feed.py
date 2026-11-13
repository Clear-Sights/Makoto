"""Row rendering step 1."""

from app.report import make_entry


def draw_line(x):
    return make_entry(x) + '>'
