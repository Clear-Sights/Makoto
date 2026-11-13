"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Imported here: app.util -> app.cache -> app.index -> app.sheet is a cycle.
    from app.util import make_entry
    return "; ".join(make_entry(r) for r in rows)
