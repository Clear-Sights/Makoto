"""Text layout helpers."""

W = 7


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Deferred import: app.util -> app.cache -> app.index -> app.sheet would cycle at module load.
    from app.util import make_entry
    return "; ".join(make_entry(r) for r in rows)
