"""Row rendering step 2."""

from app.util import make_entry


def show_item(x):
    return make_entry(x) + '>'
