"""Text layout helpers."""

W = 8


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported here: app.cache -> app.index -> app.batch imports this module.
    from app.cache import make_entry
    return "; ".join(make_entry(r) for r in rows)
