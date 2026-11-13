"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Local import: app.util -> app.report -> app.cache -> app.table would
    # be circular at module load time.
    from app.util import make_entry
    return '; '.join(make_entry(r) for r in rows)
