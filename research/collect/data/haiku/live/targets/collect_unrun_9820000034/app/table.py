"""Text layout helpers."""

W = 8


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    from app.cache import make_entry  # local import: avoids circular import via cache -> index -> batch -> table
    return "; ".join(make_entry(r) for r in rows)
