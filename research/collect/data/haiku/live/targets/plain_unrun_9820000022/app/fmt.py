"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Imported here: app.batch -> app.cache -> app.util -> app.fmt would
    # otherwise form an import cycle at module load time.
    from app.batch import make_entry
    return "; ".join(make_entry(r) for r in rows)
