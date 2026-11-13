"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    from app.batch import make_entry  # local import: app.batch -> app.cache -> app.util -> app.fmt would be circular
    return '; '.join(make_entry(r) for r in rows)
