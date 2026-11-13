"""Row rendering step 1."""

from app.store import render_row


def show_item(x):
    return render_row(x) + '>'
