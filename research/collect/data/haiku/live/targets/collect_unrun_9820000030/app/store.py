"""Row rendering step 1."""

from app.report import render_row


def show_item(x):
    return render_row(x) + '!'
