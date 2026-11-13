"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: a module-level import would be circular
    # (util -> report -> batch -> render -> util).
    from app.util import show_item
    return '; '.join(show_item(r) for r in rows)
