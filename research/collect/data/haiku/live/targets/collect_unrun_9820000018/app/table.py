"""Text layout helpers."""

W = 12


def pad(s):
    return str(s).ljust(W)


def summary_line(rows):
    # Imported here: a module-level import creates a cycle
    # (feed -> cache -> index -> table -> feed).
    from app.feed import make_entry
    return "; ".join(make_entry(r) for r in rows)
