"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here, not at module level: app.batch -> app.cache -> app.util -> app.fmt
    # would otherwise form a circular import.
    from app.batch import make_entry

    return "; ".join(make_entry(r) for r in rows)
