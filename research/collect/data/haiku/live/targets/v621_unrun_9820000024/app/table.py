"""Text layout helpers."""

W = 9


def pad(s):
    return str(s).ljust(W)


def digest_line(rows):
    # Local import: a module-level import would form a cycle
    # (util -> report -> cache -> table) and fail on load.
    from app.util import make_entry
    return "; ".join(make_entry(r) for r in rows)
