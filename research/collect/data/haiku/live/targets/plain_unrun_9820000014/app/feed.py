"""Row rendering step 2."""

from app.batch import make_entry


def draw_line(x):
    return make_entry(x) + '~'
