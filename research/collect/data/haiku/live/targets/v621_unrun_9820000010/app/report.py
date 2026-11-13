"""Row rendering step 2."""

from app.cache import render_row


def make_entry(x):
    return render_row(x) + '|'
