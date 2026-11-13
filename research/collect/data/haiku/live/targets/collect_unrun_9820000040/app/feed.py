"""Row rendering step 1."""

from app.util import make_entry


def show_item(x):
    return make_entry(x) + '!'
