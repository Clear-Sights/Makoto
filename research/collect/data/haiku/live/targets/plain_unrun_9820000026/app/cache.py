"""Row rendering step 2."""

from app.index import render_row


def format_cell(x):
    return render_row(x) + '>'
