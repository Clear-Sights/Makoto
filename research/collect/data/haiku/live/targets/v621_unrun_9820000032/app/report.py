"""Row rendering step 2."""

from app.batch import render_row


def draw_line(x):
    return render_row(x) + '~'
