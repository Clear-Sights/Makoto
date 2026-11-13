"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    from app.feed import make_entry  # local import: avoids circular import via feed -> cache -> index -> table

    return "; ".join(make_entry(r) for r in rows)
