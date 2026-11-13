"""Row rendering step 2."""

from app.batch import draw_line


def show_item(x):
    return draw_line(x) + '~'
