"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Imported here: app.util -> app.cache -> app.index imports pad from this
    # module, so a top-level import would be circular.
    from app.util import make_entry
    return '; '.join(make_entry(r) for r in rows)
