"""Row rendering step 2."""

from app.index import render_row


def draw_line(x):
    return render_row(x) + '!'
