"""Text layout helpers."""

W = 8


def pad(s):
    return str(s).ljust(W)


def overview_text(rows):
    # Imported locally: a module-level import would form a cycle
    # (cache -> index -> batch -> table) and fail at import time.
    from app.cache import make_entry
    return "; ".join(make_entry(r) for r in rows)
